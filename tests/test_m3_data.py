"""News and holdings importers, ETF holdings metric, and the export's breakdown / yield-trend / news / market blocks."""
import datetime as dt
import sqlite3
from decimal import Decimal as D
from pathlib import Path

import pytest

from irie import demo, export, ingest, storage as st
from irie.calc import etf as E
from irie.importing import import_holdings, import_news
from irie.market_calendar import load_calendar
from irie.models import Holding, Instrument, InstrumentType as T, ETFCategory as Cat, Source, SourceGrade as G
from irie.registry import Snapshot, compute_all
from irie.result import Status, publish_decision
from tests.helpers import AS_OF, INVIT, REIT

ROOT = Path(__file__).resolve().parent.parent
INST = {"T": INVIT, "E": Instrument("E", "e", T.ETF, Cat.EQUITY_BROAD, False)}
NH = "published_at,headline,summary,url,publisher,category,instrument_key\n"


def news(*rows, **kw):
    return import_news(NH + "\n".join(rows) + "\n", INST, **kw)


# ---- news importer -----------------------------------------------------------------------------------------------
def test_news_requires_a_timezone_and_a_safe_link():
    r = news("2026-10-22T09:30:00+05:30,Headline,Sum,https://x.example/a,Pub,REIT,T")
    assert r.rejected == 0 and r.accepted[0].published_at == "2026-10-22T04:00:00Z"        # normalised to UTC
    for row, code in [("2026-10-22T09:30:00,H,S,https://x.example/a,P,REIT,T", "AMBIGUOUS_TIMEZONE"),
                      ("22/10/2026,H,S,https://x.example/a,P,REIT,T", "BAD_TIMESTAMP"),
                      ("2026-10-22T09:30:00Z,H,S,javascript:alert(1),P,REIT,T", "UNSAFE_URL"),
                      ("2026-10-22T09:30:00Z,H,S,ftp://x.example/f,P,REIT,T", "UNSAFE_URL"),
                      ("2026-10-22T09:30:00Z,,S,https://x.example/a,P,REIT,T", "MISSING_HEADLINE"),
                      ("2026-10-22T09:30:00Z,H,S,https://x.example/a,P,GOSSIP,T", "BAD_CATEGORY")]:
        rep = news(row)
        assert rep.rejected == 1 and rep.codes("REJECT") == {code: 1}, (row, rep.codes())


def test_news_cleaning_review_and_dedupe():
    long = "H" * 400
    rep = news(f'2026-10-22T09:30:00Z,"{long}","a\x07b",https://x.example/a,P,INVIT,NOPE',
               "2026-10-22T09:30:00Z,Same,S,https://x.example/b,P,INVIT,T", "2026-10-22T09:30:00Z,Same,S,https://x.example/b,P,INVIT,T",
               "2026-10-23T09:30:00Z,Future,S,,P,OTHER,", now=dt.datetime(2026, 10, 22, 10, tzinfo=dt.timezone.utc))
    assert len(rep.accepted) == 3 and rep.rejected == 1 and "DUPLICATE_RECORD" in rep.codes()
    first = rep.accepted[0]
    assert len(first.headline) == 300 and "\x07" not in first.summary and first.instrument_key is None
    assert "UNKNOWN_INSTRUMENT_REF" in rep.codes() and "FUTURE_DATED" in rep.codes()


def test_news_table_refuses_a_javascript_url_even_if_the_importer_were_bypassed():
    conn = st.connect(); st.init_schema(conn)
    conn.execute("INSERT INTO source (source_id,name,grade) VALUES ('S','s','ISSUER')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO news_item (news_id,published_at,source_id,category,headline,url) VALUES ('1','2026-01-01T00:00:00Z','S','OTHER','h','javascript:x')")


# ---- holdings importer and metric -------------------------------------------------------------------------------------
HH = "instrument_key,as_of,isin,name,weight_pct,source_id\n"


def holdings_csv(n=12, total=100.0, key="E", as_of="2026-09-30"):
    w = total / n
    return HH + "\n".join(f"{key},{as_of},ISIN{i:03d},Name {i},{w}," for i in range(n)) + "\n"


def test_holdings_import_rules():
    ok = import_holdings(holdings_csv(), INST)
    assert ok.rejected == 0 and len(ok.accepted) == 12 and ok.codes() == {}
    assert sum(h.weight for h in ok.accepted).quantize(D("0.0001")) == D(1)
    assert "HOLDINGS_WEIGHT_SUM" in import_holdings(holdings_csv(total=80), INST).codes()
    bad = [(HH + "T,2026-09-30,I,n,5,", "HOLDINGS_ONLY_FOR_ETF"), (HH + "E,2026-09-30,I,n,150,", "BAD_WEIGHT"),
           (HH + "E,2026-09-30,I,n,,", "BAD_WEIGHT"), (HH + "E,2026-09-30,,n,5,", "MISSING_IDENTITY"),
           (HH + "X,2026-09-30,I,n,5,", "UNKNOWN_INSTRUMENT"), (HH + "E,30/09/2026,I,n,5,", "BAD_VALUE")]
    for text, code in bad:
        r = import_holdings(text + "\n", INST)
        assert r.rejected == 1 and code in r.codes("REJECT"), (text, r.codes())
    dup = import_holdings(HH + "E,2026-09-30,I,n,5,\nE,2026-09-30,I,n,6,\nE,2026-09-30,I,n,5,\n", INST)
    assert dup.rejected == 2 and dup.codes("REJECT") == {"CONFLICTING_DUPLICATE": 1, "DUPLICATE_RECORD": 1}


def hold(rep):
    return rep.accepted


def test_top10_weight_definition_and_refusals():
    etf = INST["E"]
    flat = hold(import_holdings(holdings_csv(20), INST))                           # 20 x 5%
    r = E.holdings_top10_weight(etf, flat, AS_OF)
    assert r.value == D("0.5") and not r.flags
    assert E.holdings_top10_weight(etf, hold(import_holdings(holdings_csv(5), INST)), AS_OF).flags == ("FEWER_THAN_10_HOLDINGS",)
    assert E.holdings_top10_weight(etf, hold(import_holdings(holdings_csv(5), INST)), AS_OF).value == D(1)
    partial = E.holdings_top10_weight(etf, hold(import_holdings(holdings_csv(20, total=70), INST)), AS_OF)
    assert partial.value is None and "HOLDINGS_INCOMPLETE" in partial.reasons[0]    # a partial list is refused, not summed
    assert E.holdings_top10_weight(etf, [], AS_OF).reasons == ("HOLDINGS_NOT_SUPPLIED",)
    old = E.holdings_top10_weight(etf, hold(import_holdings(holdings_csv(20, as_of="2026-07-01"), INST)), AS_OF)
    assert old.ok and "HOLDINGS_STALE" in old.flags
    assert not publish_decision(old.with_flags(), {})[0]
    future = E.holdings_top10_weight(etf, hold(import_holdings(holdings_csv(20, as_of="2026-12-01"), INST)), AS_OF)
    assert future.reasons == ("HOLDINGS_NOT_SUPPLIED",)                             # not-yet-valid disclosures are ignored


def test_latest_portfolio_wins_and_applicability():
    etf = INST["E"]
    both = hold(import_holdings(holdings_csv(20, as_of="2026-08-31") + holdings_csv(10, as_of="2026-09-30").split("\n", 1)[1], INST))
    assert E.holdings_top10_weight(etf, both, AS_OF).value == D(1)                  # 10 x 10% from the later date
    gold = Instrument("G", "g", T.ETF, Cat.GOLD_SILVER, False)
    out = compute_all(Snapshot(gold, AS_OF))
    assert out["holdings_top10_weight"].status is Status.NOT_APPLICABLE
    assert compute_all(Snapshot(REIT, AS_OF))["holdings_top10_weight"].status is Status.NOT_APPLICABLE


# ---- export blocks ----------------------------------------------------------------------------------------------------
CAL = load_calendar(ROOT / "config" / "market_calendar.json")


@pytest.fixture(scope="module")
def demo_ds(tmp_path_factory):
    d = tmp_path_factory.mktemp("m3")
    demo.write_demo_inbox(d)
    conn = st.connect(); st.init_schema(conn)
    reg = demo.demo_registry()
    ingest.run_cycle(conn, reg, {k: ingest.FileInboxFetcher(d, lambda: demo.DEMO_NOW) for k in reg}, lambda: demo.DEMO_NOW, calendar=CAL)
    return conn, reg, export.build_dataset(conn, reg, demo.DEMO_NOW, "public", CAL)


def by(ds):
    return {i["key"]: i for i in ds["instruments"]}


def test_component_breakdown_keeps_capital_out_of_income(demo_ds):
    _, _, ds = demo_ds
    r = by(ds)["DEMO_REIT_A"]["breakdown"]
    # the REIT's headline is withheld (price discrepancy) but its distributions are verified: breakdown is about distributions
    assert r["available"] and set(r["per_unit"]) >= {"interest", "dividend", "rental", "capital_repayment"}
    a = by(ds)["DEMO_INVIT_A"]["breakdown"]
    assert a["available"] and "rental" not in a["per_unit"]
    assert abs(a["income_per_unit"] + a["other_per_unit"] + a["capital_per_unit"] - a["total"]) < 0.02
    assert a["capital_per_unit"] > 0 and abs(sum(v for v in a["share"].values()) - 1) < 0.01
    assert a["income_per_unit"] == pytest.approx(a["per_unit"]["interest"] + a["per_unit"]["dividend"])
    assert by(ds)["DEMO_INVIT_B"]["breakdown"]["available"] is False and by(ds)["DEMO_INVIT_B"]["breakdown"]["coverage"] == "NONE"
    assert by(ds)["DEMO_INVIT_C"]["breakdown"]["available"] is False                         # unverified source: withheld
    assert by(ds)["DEMO_ETF_EQ"]["breakdown"] is None                                         # no split ever invented for an ETF


def test_yield_trend_is_emitted_only_for_reliable_points(demo_ds):
    _, _, ds = demo_ds
    a = by(ds)["DEMO_INVIT_A"]["history"]["yield_trend"]
    assert 20 <= len(a) <= 60 and all(0 < y < 0.3 for _, y in a)
    assert min(d for d, _ in a) >= "2025-11-14"                       # a full trailing year must sit inside the recorded history
    assert by(ds)["DEMO_INVIT_C"]["history"]["yield_trend"] == []        # aggregator-grade payments
    assert by(ds)["DEMO_ETF_EQ"]["history"]["yield_trend"] == []
    reit = by(ds)["DEMO_REIT_A"]["history"]["yield_trend"]
    assert "2026-10-21" not in [d for d, _ in reit]                      # the date with an open price discrepancy is never charted


def test_holdings_in_export_and_stale_metric_withheld(demo_ds):
    _, _, ds = demo_ds
    eq, debt = by(ds)["DEMO_ETF_EQ"], by(ds)["DEMO_ETF_DEBT"]
    assert len(eq["holdings"]) == 10 and eq["holdings"][0]["weight"] == 0.35 and eq["metrics"]["holdings_top10_weight"]["value"] == pytest.approx(0.905)
    assert debt["metrics"]["holdings_top10_weight"]["value"] is None and "HOLDINGS_STALE" in debt["metrics"]["holdings_top10_weight"]["flags"]
    assert by(ds)["DEMO_ETF_GOLD"]["holdings"] == [] and "holdings_top10_weight" not in by(ds)["DEMO_ETF_GOLD"]["metrics"]


def test_news_block_is_gated_labelled_and_filterable(demo_ds):
    conn, reg, ds = demo_ds
    n = ds["news"]
    assert len(n["items"]) == 7 and n["feed_connected"] and all(i["synthetic"] for i in n["items"])
    assert all(i["headline"].startswith("SYNTHETIC EXAMPLE") and i["url"].startswith("https://example.invalid/") for i in n["items"])
    assert {i["category"] for i in n["items"]} == {"REIT", "INVIT", "INFRASTRUCTURE", "CORPORATE"}
    ts = [i["published_at"] for i in n["items"]]
    assert ts == sorted(ts, reverse=True) and all(i["retrieved_at"] == "2026-10-22T10:00:00Z" for i in n["items"])


def test_market_and_schedule_blocks(demo_ds):
    conn, reg, ds = demo_ds
    assert ds["market"]["known"] and ds["market"]["open"] and ds["market"]["calendar_verified"] is False
    assert ds["market"]["session"] == "09:15-15:30 IST" and ds["market"]["next_open"] == "2026-10-23T03:45:00Z"
    assert ds["synthetic"] is True and ds["notice"].startswith("SYNTHETIC DEMO DATA")
    s = {x["id"]: x for x in ds["sources"]}["DEMO"]
    assert s["schedule"] == "local" and s["next_attempt_at"] == "2026-10-22T11:00:00Z" and s["synthetic"]
    sat = dt.datetime(2026, 10, 24, 6, tzinfo=dt.timezone.utc)
    m = export.build_dataset(conn, reg, sat, "public", CAL)["market"]
    assert not m["open"] and m["reason"] == "WEEKEND" and m["next_open"] == "2026-10-26T03:45:00Z"
    assert export.build_dataset(conn, reg, sat, "public")["market"] == {"known": False}      # honest when no calendar is given
