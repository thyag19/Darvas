"""Acquisition cycle, source registry, freshness, discrepancy handling and export gating. No network, no real data."""
import dataclasses
import datetime as dt
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from irie import cli, demo, discrepancy as dsc, export, freshness as fr, ingest, storage as st
from irie.models import SourceGrade as G
from irie.sources import Access, RegistryError, SourceSpec, load_registry, parse_registry, validate
from tests.helpers import AS_OF, ev

ROOT = Path(__file__).resolve().parent.parent
T0 = dt.datetime(2026, 10, 22, 10, 0, tzinfo=dt.timezone.utc)
HOUR = dt.timedelta(hours=1)


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += dt.timedelta(**kw)


def spec(sid="INBOX", **kw):
    base = dict(source_id=sid, name=sid, grade=G.ISSUER, kind="file_inbox", access=Access.USER_SUPPLIED,
                min_interval_s=0, max_staleness_s=7200, cadence_s=3600)
    base.update(kw)
    return SourceSpec(**base)


INSTR = "key,name,type,etf_category,distributes\nI1,Inst One,INVIT,,\nE1,Etf One,ETF,EQUITY_BROAD,N\n"
DIST = ("instrument_key,ex_date,record_date,total_per_unit,interest,dividend,capital_repayment,include,amount_grade,source_id\n"
        "I1,2026-08-01,2026-08-01,3.0,2.0,0.5,0.5,Y,ISSUER,S9\n")
PRICE = "instrument_key,date,price,venue\nI1,2026-10-21,100,NSE\nE1,2026-10-21,50,NSE\n"


@pytest.fixture()
def env(tmp_path):
    conn = st.connect()
    st.init_schema(conn)
    clock = Clock()
    inbox = tmp_path / "inbox"
    (inbox / "INBOX").mkdir(parents=True)
    reg = {"INBOX": spec()}
    fetchers = {"INBOX": ingest.FileInboxFetcher(inbox, clock)}
    return dict(conn=conn, clock=clock, inbox=inbox / "INBOX", reg=reg, fetchers=fetchers)


def cycle(env, **kw):
    return ingest.run_cycle(env["conn"], env["reg"], env["fetchers"], env["clock"], sleep=lambda s: None, **kw)


def drop(env, name, text):
    (env["inbox"] / name).write_text(text)


# ---- registry ------------------------------------------------------------------------------------------
def test_shipped_registry_clears_nothing():
    reg = load_registry(ROOT / "config" / "sources.json")
    assert not any(s.display_cleared for s in reg.values())
    assert not any(s.access is Access.CLEARED for s in reg.values())
    assert {s.source_id for s in reg.values() if s.may_fetch} == {"INBOX"}


def test_registry_validation_rules():
    base = {"source_id": "X", "name": "x", "grade": "EXCHANGE", "kind": "http", "access": "NOT_CLEARED"}
    with pytest.raises(RegistryError, match="CLEARED needs"):
        parse_registry({"sources": [{**base, "access": "CLEARED"}]})
    with pytest.raises(RegistryError, match="display_cleared needs"):
        parse_registry({"sources": [{**base, "access": "USER_SUPPLIED", "kind": "file_inbox", "display_cleared": True}]})
    with pytest.raises(RegistryError, match="NOT_CLEARED source"):
        parse_registry({"sources": [{**base, "display_cleared": True, "display_evidence": "e", "terms_checked_on": "2026-01-01"}]})
    with pytest.raises(RegistryError, match="duplicate"):
        parse_registry({"sources": [base, base]})
    ok = parse_registry({"sources": [{**base, "access": "CLEARED", "clearance_evidence": "letter 2026-10-01", "terms_checked_on": "2026-10-01"}]})
    assert ok["X"].may_fetch


# ---- retries and rate limiting ---------------------------------------------------------------------------
def test_retries_backoff_and_permanent_errors():
    calls, sleeps = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ingest.FetchError("503")
        return "ok"
    assert ingest.with_retries(flaky, 3, 1.0, sleep=sleeps.append, rng=lambda: 1.0) == ("ok", 3)
    assert sleeps == [1.0, 2.0]                                   # exponential
    with pytest.raises(ingest.FetchError, match="gave up after 2"):
        ingest.with_retries(lambda: (_ for _ in ()).throw(ingest.FetchError("x")), 2, sleep=lambda s: None)
    n = []
    with pytest.raises(ingest.PermanentFetchError):
        ingest.with_retries(lambda: n.append(1) or (_ for _ in ()).throw(ingest.PermanentFetchError("403")), 5, sleep=lambda s: None)
    assert len(n) == 1                                            # never retried


def test_rate_limiter_enforces_minimum_gap():
    t, sleeps = [0.0], []
    rl = ingest.RateLimiter(5.0, clock=lambda: t[0], sleep=sleeps.append)
    rl.wait()
    t[0] = 2.0
    rl.wait()
    assert sleeps == [3.0]


# ---- cycle ------------------------------------------------------------------------------------------------
def test_not_cleared_sources_are_logged_but_never_fetched():
    class Boom:
        def fetch(self, spec, as_of, kinds=None):
            raise AssertionError("fetched a NOT_CLEARED source")
    conn = st.connect(); st.init_schema(conn)
    reg = load_registry(ROOT / "config" / "sources.json")
    class Empty:
        def fetch(self, spec, as_of, kinds=None):
            return []
    fetchers = {k: (Empty() if reg[k].may_fetch else Boom()) for k in reg}
    rep = ingest.run_cycle(conn, reg, fetchers, Clock(), sleep=lambda s: None)
    status = {o.source_id: o.status for o in rep.outcomes}
    assert status["NSE"] == status["BSE"] == status["AMFI"] == status["ISSUER"] == "SKIPPED_NOT_CLEARED"
    assert conn.execute("SELECT COUNT(*) FROM retrieval_log").fetchone()[0] == len(reg)   # attempts are auditable
    stat = {s.source_id: s.freshness for s in ingest.source_statuses(conn, reg, T0)}
    assert stat["NSE"] is fr.Freshness.NOT_FETCHED


def test_cycle_ingests_with_separate_retrieval_and_observation_times(env):
    drop(env, "instruments_a.csv", INSTR); drop(env, "distributions_a.csv", DIST); drop(env, "prices_a.csv", PRICE)
    rep = cycle(env)
    o = rep.outcomes[0]
    assert o.status == "OK" and o.documents == 3 and o.rejected == 0 and o.observed_through == dt.date(2026, 10, 21)
    row = env["conn"].execute("SELECT trade_date, retrieved_at FROM price_eod WHERE instrument_key='I1'").fetchone()
    assert row == ("2026-10-21", "2026-10-22T10:00:00Z")          # observed 21st, retrieved 22nd
    log = env["conn"].execute("SELECT observed_through, started_at FROM retrieval_log").fetchone()
    assert log == ("2026-10-21", "2026-10-22T10:00:00Z")


def test_files_are_processed_in_dependency_order_and_late_instruments_trigger_retry(env):
    drop(env, "distributions_a.csv", DIST)                         # alphabetically first, but needs instruments
    drop(env, "instruments_a.csv", INSTR)
    assert cycle(env).outcomes[0].rejected == 0
    # distributions first, instruments arrive in a later cycle
    env2 = dict(env, conn=st.connect())
    st.init_schema(env2["conn"])
    (env["inbox"] / "instruments_a.csv").unlink()
    first = cycle(env2)
    assert first.outcomes[0].rejected == 1
    drop(env, "instruments_a.csv", INSTR)
    env["clock"].advance(hours=1)
    second = cycle(env2)
    assert second.outcomes[0].rejected == 0 and env2["conn"].execute("SELECT COUNT(*) FROM distribution_event").fetchone()[0] == 1


def test_cycle_is_idempotent_and_respects_cadence(env):
    drop(env, "instruments_a.csv", INSTR); drop(env, "distributions_a.csv", DIST); drop(env, "prices_a.csv", PRICE)
    cycle(env)
    counts = lambda: [env["conn"].execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("price_eod", "distribution_event", "source_document")]
    before = counts()
    env["clock"].advance(minutes=10)
    assert cycle(env).outcomes[0].status == "SKIPPED_NOT_DUE"
    assert cycle(env, force=True).outcomes[0].duplicates == 3 and counts() == before
    env["clock"].advance(hours=1)
    assert cycle(env).outcomes[0].status == "NO_NEW_DATA" and counts() == before
    assert env["conn"].execute("SELECT COUNT(*) FROM retrieval_log").fetchone()[0] == 4


def test_failure_is_isolated_retried_and_makes_source_stale(env):
    class Down:
        n = 0
        def fetch(self, spec, as_of, kinds=None):
            Down.n += 1
            raise ingest.FetchError("timeout")
    reg = {"INBOX": spec(), "BAD": spec("BAD", max_attempts=3)}
    drop(env, "instruments_a.csv", INSTR)
    fetchers = {"INBOX": env["fetchers"]["INBOX"], "BAD": Down()}
    rep = ingest.run_cycle(env["conn"], reg, fetchers, env["clock"], sleep=lambda s: None)
    o = {x.source_id: x for x in rep.outcomes}
    assert o["INBOX"].status == "OK" and o["BAD"].status == "ERROR" and o["BAD"].attempts == 0 and Down.n == 3
    assert "gave up after 3 attempts" in o["BAD"].error
    stat = lambda t: {s.source_id: s for s in ingest.source_statuses(env["conn"], reg, t)}
    assert stat(T0)["BAD"].freshness is fr.Freshness.NEVER and stat(T0)["BAD"].consecutive_failures == 1
    assert stat(T0)["INBOX"].freshness is fr.Freshness.FRESH
    assert stat(T0 + dt.timedelta(hours=3))["INBOX"].freshness is fr.Freshness.STALE      # > max_staleness 2h


def test_bad_documents_are_rejected_without_stopping_the_cycle(env):
    drop(env, "instruments_a.csv", INSTR)
    (env["inbox"] / "prices_bin.csv").write_bytes(b"\xff\xfe\x00bad")
    drop(env, "mystery.csv", "a,b\n1,2\n")
    drop(env, "distributions_nocol.csv", "instrument_key,ex_date\nI1,2026-01-01\n")
    drop(env, "prices_ok.csv", PRICE)
    o = cycle(env).outcomes[0]
    assert o.rejected == 3 and o.accepted == 4 and "not UTF-8" in o.error and "must start with" in o.error and "missing required column" in o.error
    assert env["conn"].execute("SELECT COUNT(*) FROM price_eod").fetchone()[0] == 2


def test_document_hash_mismatch_is_a_permanent_error(env):
    class Tampered:
        def fetch(self, spec, as_of, kinds=None):
            return [ingest.RawDocument("INBOX", "prices_x.csv", T0, "0" * 64, PRICE.encode())]
    rep = ingest.run_cycle(env["conn"], env["reg"], {"INBOX": Tampered()}, env["clock"], sleep=lambda s: None)
    assert rep.outcomes[0].status == "ERROR" and "sha256" in rep.outcomes[0].error


def test_unknown_row_source_is_attributed_to_the_provider_with_provenance_kept(env):
    drop(env, "instruments_a.csv", INSTR); drop(env, "distributions_a.csv", DIST)
    cycle(env)
    src, notes = env["conn"].execute("SELECT source_id, notes FROM distribution_event").fetchone()
    assert src == "INBOX" and "original_source_id=S9" in notes


# ---- freshness ----------------------------------------------------------------------------------------------
def test_ist_date_and_due_logic():
    assert fr.ist_date(dt.datetime(2026, 10, 21, 19, 0, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 22)   # 00:30 IST
    assert fr.ist_date(dt.datetime(2026, 10, 21, 18, 0, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 21)
    s = spec()
    assert fr.is_due(s, None, T0) and fr.is_due(s, "2026-10-22T09:00:30Z", T0) and not fr.is_due(s, "2026-10-22T09:30:00Z", T0)
    with pytest.raises(ValueError):
        fr.utc_iso(dt.datetime(2026, 1, 1))


# ---- discrepancy ----------------------------------------------------------------------------------------------
def obs(sid, grade, value, r="2026-10-22T10:00:00Z"):
    return dsc.Obs(sid, grade, dt.date(2026, 10, 21), D(value), r)


def test_resolve_rules():
    one, d = dsc.resolve("K", "price", [obs("A", G.EXCHANGE, "100")])
    assert one.source_id == "A" and not d
    c, d = dsc.resolve("K", "price", [obs("A", G.EXCHANGE, "100"), obs("B", G.AGGREGATOR, "100.004")])
    assert c.source_id == "A" and not d                              # corroborated within Rs0.005
    c, d = dsc.resolve("K", "price", [obs("A", G.EXCHANGE, "100"), obs("B", G.AGGREGATOR, "101")])
    assert c.source_id == "A" and len(d) == 1 and d[0].abs_diff == D(1)   # higher grade wins, disagreement recorded
    c, d = dsc.resolve("K", "price", [obs("A", G.ISSUER, "100"), obs("B", G.ISSUER, "101")])
    assert c is None and len(d) == 1                                 # tie: never pick arbitrarily


def test_reconcile_events_never_double_counts_and_flags_conflicts():
    a = ev("2026-08-01", 3, grade=G.EXCHANGE, sid="A")
    b = ev("2026-08-01", 3.002, grade=G.AGGREGATOR, sid="B")
    out, d = dsc.reconcile_events([a, b])
    assert not d and sum(e.total_per_unit for e in out if e.include) == D(3)       # counted once
    c = ev("2026-08-01", 4, grade=G.AGGREGATOR, sid="B")
    out, d = dsc.reconcile_events([a, c])
    assert len(d) == 1 and [e.source_id for e in out if e.include] == ["A"]
    t1, t2 = ev("2026-08-01", 3, grade=G.ISSUER, sid="A"), ev("2026-08-01", 4, grade=G.ISSUER, sid="B")
    out, d = dsc.reconcile_events([t1, t2])
    assert len(d) == 1 and not any(e.include for e in out) and any(e.total_per_unit is None for e in out)
    same = [ev("2026-08-01", 1, sid="A"), ev("2026-08-01", 2, sid="A")]
    assert sum(e.total_per_unit for e in dsc.reconcile_events(same)[0]) == D(3)       # one source: additive


def test_tied_discrepancy_makes_ttm_a_flagged_lower_bound():
    from irie.calc.distributions import analyze_distributions
    from tests.helpers import INVIT, px
    t1, t2 = ev("2026-08-01", 3, grade=G.ISSUER, sid="A"), ev("2026-08-01", 4, grade=G.ISSUER, sid="B")
    other = ev("2026-05-01", 2, grade=G.ISSUER, sid="A")
    out, _ = dsc.reconcile_events([t1, t2, other])
    m = analyze_distributions(INVIT, out, px(100), AS_OF).metrics["ttm_dpu"]
    assert m.value == D(2) and "AMOUNT_UNAVAILABLE_IN_WINDOW" in m.flags


def test_discrepancies_are_persisted_once_and_history_survives(env):
    env["reg"]["B"] = spec("B", grade=G.AGGREGATOR)
    (env["inbox"].parent / "B").mkdir()
    env["fetchers"]["B"] = ingest.FileInboxFetcher(env["inbox"].parent, env["clock"])
    drop(env, "instruments_a.csv", INSTR); drop(env, "prices_a.csv", PRICE)
    (env["inbox"].parent / "B" / "prices_b.csv").write_text("instrument_key,date,price,venue\nI1,2026-10-21,103,NSE\n")
    r1 = cycle(env)
    assert r1.discrepancies_new == 1
    env["conn"].execute("UPDATE discrepancy SET status='RESOLVED', resolution_note='checked with issuer'")
    env["clock"].advance(hours=1)
    cycle(env)
    rows = env["conn"].execute("SELECT status, resolution_note FROM discrepancy").fetchall()
    assert rows == [("RESOLVED", "checked with issuer")]            # never reopened or duplicated
    assert env["conn"].execute("SELECT COUNT(*) FROM price_eod WHERE instrument_key='I1'").fetchone()[0] == 2   # both kept


# ---- export gating -----------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def demo_db(tmp_path_factory):
    d = tmp_path_factory.mktemp("demo")
    demo.write_demo_inbox(d)
    conn = st.connect(); st.init_schema(conn)
    reg = demo.demo_registry()
    ingest.run_cycle(conn, reg, {k: ingest.FileInboxFetcher(d, lambda: demo.DEMO_NOW) for k in reg}, lambda: demo.DEMO_NOW)
    return conn, reg


def by_key(ds):
    return {i["key"]: i for i in ds["instruments"]}


def test_public_export_withholds_unverified_and_discrepant_values(demo_db):
    conn, reg = demo_db
    inst = by_key(export.build_dataset(conn, reg, demo.DEMO_NOW, "public"))
    a, c, r = inst["DEMO_INVIT_A"], inst["DEMO_INVIT_C"], inst["DEMO_REIT_A"]
    assert a["metrics"]["ttm_yield"]["value"] is not None
    assert c["metrics"]["ttm_yield"]["value"] is None and c["metrics"]["ttm_yield"]["withheld"]       # aggregator-grade amounts
    assert "UNVERIFIED_SOURCE" in c["metrics"]["ttm_yield"]["flags"]
    assert r["metrics"]["ttm_yield"]["value"] is None and "SOURCE_DISCREPANCY" in r["metrics"]["ttm_yield"]["flags"]
    assert r["open_discrepancies"] and r["open_discrepancies"][0]["field"] == "price"


def test_nothing_cleared_means_nothing_published(demo_db):
    conn, reg = demo_db
    closed = {k: dataclasses.replace(v, display_cleared=False, display_evidence="") for k, v in reg.items()}
    conn2 = st.connect(); st.init_schema(conn2)
    conn.backup(conn2)
    st.sync_sources(conn2, [s.to_source() for s in closed.values()])
    ds = export.build_dataset(conn2, closed, demo.DEMO_NOW, "public")
    for i in ds["instruments"]:
        assert all(m["value"] is None for m in i["metrics"].values())
        assert i["history"]["distributions"] == [] and i["history"]["prices"] == []
        assert i["latest"]["price"]["value"] is None
        assert i["history"]["yield_trend"] == [] and i["holdings"] == []
        assert not (i["breakdown"] or {}).get("available")          # component breakdown withheld too
    assert ds["news"]["items"] == [] and ds["news"]["withheld"] == 7   # headlines are third-party content: gated like prices
    assert any(m["withheld"] for i in ds["instruments"] for m in i["metrics"].values())
    pv = export.build_dataset(conn2, closed, demo.DEMO_NOW, "preview")
    assert pv["preview"] and "Do not deploy" in pv["notice"]
    assert by_key(pv)["DEMO_INVIT_A"]["metrics"]["ttm_yield"]["value"] is not None


def test_export_invariants_unavailable_is_never_a_number_and_capital_is_never_income(demo_db):
    conn, reg = demo_db
    ds = export.build_dataset(conn, reg, demo.DEMO_NOW, "preview")
    text = export.dumps(ds)                                          # allow_nan=False: no NaN/Infinity leaks
    for i in ds["instruments"]:
        for n, m in i["metrics"].items():
            if m["status"] != "OK":
                assert m["value"] is None, (i["key"], n)
        m = i["metrics"]
        if all(m.get(k, {}).get("value") is not None for k in ("income_yield", "other_yield", "capital_repayment_yield", "ttm_yield")):
            tot = m["income_yield"]["value"] + m["other_yield"]["value"] + m["capital_repayment_yield"]["value"]
            assert abs(tot - m["ttm_yield"]["value"]) < 1e-3
    a = by_key(ds)["DEMO_INVIT_A"]["metrics"]
    assert a["capital_repayment_yield"]["value"] > 0 and a["income_yield"]["value"] < a["ttm_yield"]["value"]   # capital kept out of income
    b = by_key(ds)["DEMO_INVIT_B"]["metrics"]
    assert b["income_yield"]["value"] is None and b["income_yield"]["status"] == "UNAVAILABLE"                  # no split => unavailable, not 0
    gold = by_key(ds)["DEMO_ETF_GOLD"]["metrics"]
    assert "ttm_dpu" not in gold and "income_yield" not in gold            # no InvIT/REIT metric is ever applied to an ETF
    assert "trailing_distribution_yield" not in gold                       # non-distributing scheme: not applicable, so omitted
    assert "trailing_distribution_yield" in by_key(ds)["DEMO_ETF_DEBT"]["metrics"]
    assert json.loads(text)["schema_version"] == 1


def test_cli_run_cycle_and_public_build_with_the_shipped_registry(tmp_path, capsys):
    inbox = tmp_path / "inbox" / "INBOX"
    inbox.mkdir(parents=True)
    (inbox / "instruments_a.csv").write_text(INSTR)
    (inbox / "prices_a.csv").write_text(PRICE.replace("2026-10-21", "2026-10-01"))
    db = str(tmp_path / "irie.sqlite")
    reg = str(ROOT / "config" / "sources.json")
    assert cli.main(["run-cycle", "--db", db, "--registry", reg, "--inbox", str(tmp_path / "inbox")]) == 0
    assert '"NSE": {"accepted": 0' in capsys.readouterr().out
    out = tmp_path / "site"
    assert cli.main(["build-site", "--db", db, "--registry", reg, "--out", str(out)]) == 0
    ds = json.loads((out / "data.json").read_text())
    assert len(ds["instruments"]) == 2 and ds["mode"] == "public"
    assert all(m["value"] is None for i in ds["instruments"] for m in i["metrics"].values())   # INBOX is not display-cleared
    assert (out / "index.html").exists() and (out / "app.js").exists()


def test_a_figure_without_source_attribution_is_never_publishable():
    from irie.models import Source
    from irie.result import MetricResult, Status, publish_decision
    r = MetricResult("m", Status.OK, AS_OF, D(1))
    ok_, why = publish_decision(r, {})
    assert not ok_ and "no source attribution" in why
