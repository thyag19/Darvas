import datetime as dt
import json
import sqlite3
from decimal import Decimal as D

import pytest

from irie import cli, storage
from irie.importing import import_distributions, import_navs, import_prices
from irie.models import Instrument, InstrumentType as T, Source, SourceGrade as G
from irie.registry import Snapshot, compute_all
from irie.result import MetricResult, Status, publish_decision
from tests.helpers import AS_OF, INVIT, REIT, ev, px

INST = {"T": INVIT, "R": REIT, "E": Instrument("E", "e", T.ETF)}
HDR = "instrument_key,ex_date,record_date,total_per_unit,interest,dividend,rental,other_income,capital_repayment,include,amount_grade,source_id\n"


def imp(rows, **kw):
    return import_distributions(HDR + "\n".join(rows) + "\n", INST, **kw)


def only_code(rep, code):
    return [i for i in rep.issues if i.code == code]


def test_clean_row_is_accepted_with_exact_decimals():
    rep = imp(["T,2026-08-01,2026-08-01,4.12,2.6909,0.0224,,,1.4067,Y,EXCHANGE,S14"])
    assert rep.rejected == 0 and len(rep.accepted) == 1
    e = rep.accepted[0]
    assert e.total_per_unit == D("4.12") and e.components and sum(e.components.values()) == D("4.12")


@pytest.mark.parametrize("row,code", [
    (",2026-08-01,,4,,,,,,Y,EXCHANGE,S", "MISSING_INSTRUMENT_KEY"),
    ("X,2026-08-01,,4,,,,,,Y,EXCHANGE,S", "UNKNOWN_INSTRUMENT"),
    ("T,,,4,,,,,,Y,EXCHANGE,S", "MISSING_EX_DATE"),
    ("T,01/08/2026,,4,,,,,,Y,EXCHANGE,S", "BAD_DATE"),            # ambiguous dd/mm form is never guessed
    ("T,2026-08-01,not-a-date,4,,,,,,Y,EXCHANGE,S", "BAD_DATE"),
    ("T,2026-08-01,,four,,,,,,Y,EXCHANGE,S", "BAD_NUMBER"),
    ("T,2026-08-01,,NaN,,,,,,Y,EXCHANGE,S", "BAD_NUMBER"),
    ("T,2026-08-01,,-4,,,,,,Y,EXCHANGE,S", "NEGATIVE_AMOUNT"),
    ("T,2026-08-01,,4,-1,,,,,Y,EXCHANGE,S", "NEGATIVE_AMOUNT"),
    ("T,2026-08-01,,4,,,3,,,Y,EXCHANGE,S", "COMPONENT_NOT_ALLOWED"),   # rental is not an InvIT component
    ("E,2026-08-01,,4,4,,,,,Y,EXCHANGE,S", "COMPONENT_NOT_ALLOWED"),   # ETFs never get a component split
    ("T,2026-08-01,,4,,,,,,maybe,EXCHANGE,S", "BAD_INCLUDE_FLAG"),
    ("T,2026-08-01,,4,,,,,,Y,GOSSIP,S", "BAD_GRADE"),
])
def test_rejections(row, code):
    rep = imp([row])
    assert rep.rejected == 1 and not rep.accepted
    assert only_code(rep, code)


def test_exact_duplicate_rejected_but_same_date_different_amount_is_review_not_rejected():
    r = "T,2026-08-01,,4,,,,,,Y,EXCHANGE,S14"
    rep = imp([r, r])
    assert rep.rejected == 1 and only_code(rep, "DUPLICATE_RECORD")
    rep2 = imp([r, "T,2026-08-01,,2.5,,,,,,Y,EXCHANGE,S14"])
    assert rep2.rejected == 0 and len(rep2.accepted) == 2
    assert len(only_code(rep2, "SAME_EX_DATE_MULTIPLE_RECORDS")) == 2


def test_ambiguous_rows_are_accepted_but_flagged():
    rep = imp([
        "T,2026-08-01,2026-07-30,4,,,,,,Y,EXCHANGE,S14",                       # record before ex
        "T,2026-05-01,2026-05-09,4,,,,,,Y,EXCHANGE,S14",                       # 8-day gap
        "T,2026-02-01,,4,3,,,,,Y,EXCHANGE,S14",                                # components != total
        "T,2025-11-01,,,,,,,,Y,EXCHANGE,S14",                                  # include=Y, no amount
        "T,2025-08-01,,,2,,,,,N,EXCHANGE,S14",                                 # components, no total
        "T,2026-12-01,,4,,,,,,Y,EXCHANGE,S14",                                 # after as_of
        "T,2025-05-01,,4,,,,,,Y,AGGREGATOR,S1",
    ], as_of=AS_OF, known_sources={"S14": 1})
    codes = rep.codes()
    assert rep.rejected == 0 and len(rep.accepted) == 7
    for c in ("RECORD_BEFORE_EX_DATE", "RECORD_DATE_GAP", "COMPONENTS_DO_NOT_RECONCILE", "INCLUDE_WITHOUT_AMOUNT",
              "COMPONENTS_WITHOUT_TOTAL", "EX_DATE_AFTER_AS_OF", "UNKNOWN_SOURCE_ID", "UNVERIFIED_AMOUNT_SOURCE"):
        assert c in codes, c
    no_amount = [e for e in rep.accepted if e.total_per_unit is None]
    assert len(no_amount) == 2 and all(not e.include for e in no_amount)       # never silently zero, never included


def test_blank_amount_is_none_not_zero():
    rep = imp(["T,2026-08-01,,,,,,,,N,EXCHANGE,S14"])
    assert rep.accepted[0].total_per_unit is None and rep.accepted[0].components == {}


def test_missing_required_column_is_an_error():
    with pytest.raises(ValueError, match="missing required column"):
        import_distributions("instrument_key,ex_date\nT,2026-01-01\n", INST)


def test_report_is_reproducible_and_ids_are_stable_under_reordering():
    rows = ["T,2026-08-01,,4,,,,,,Y,EXCHANGE,S14", "T,2026-05-01,,3,,,,,,Y,EXCHANGE,S14", "T,x,,3,,,,,,Y,EXCHANGE,S14"]
    a, b = imp(rows), imp(rows)
    assert a.to_json() == b.to_json() and a.summary()["file_sha256"] == b.summary()["file_sha256"]
    c = imp(list(reversed(rows)))
    assert {e.event_id for e in a.accepted} == {e.event_id for e in c.accepted}
    assert json.loads(a.to_json())["issues"][0]["input"]["ex_date"] == "x"     # the original row is reported back


def test_every_input_row_is_accounted_for(bundle):
    rep = bundle.report
    assert rep.rows_read == len(rep.accepted) + rep.rejected


def test_price_and_nav_import():
    p = import_prices("instrument_key,date,price,venue\nT,2026-10-21,100.5,NSE\nT,2026-10-21,100.5,NSE\n"
                      "T,2026-10-20,0,NSE\nT,2026-10-22,99,NSE\nT,2026-10-19,,NSE\nT,2026-10-19,abc,NSE\n"
                      "T,2026-10-18,98,NSE\nT,2026-10-18,97,NSE\n", INST, as_of=AS_OF)
    assert len(p.accepted) == 2 and p.rejected == 6
    assert p.codes("REJECT") == {"BAD_NUMBER": 1, "CONFLICTING_DUPLICATE": 1, "DATE_AFTER_AS_OF": 1,
                                 "DUPLICATE_RECORD": 1, "PRICE_NOT_POSITIVE": 2}
    n = import_navs("instrument_key,nav_date,nav,kind,grade\nT,2026-06-30,146.93,FAIR_VALUE,ISSUER\n"
                    "T,2026-06-30,150,FAIR_VALUE,ISSUER\nT,2026-06-30,150,BOGUS,ISSUER\nT,2026-06-30,-1,FAIR_VALUE,ISSUER\n",
                    INST, as_of=AS_OF)
    assert len(n.accepted) == 1 and n.rejected == 3


def test_cli_validate_exit_codes(tmp_path, capsys):
    (tmp_path / "i.csv").write_text("key,name,type\nT,t,INVIT\n")
    (tmp_path / "good.csv").write_text(HDR + "T,2026-08-01,,4,,,,,,Y,EXCHANGE,S14\n")
    (tmp_path / "bad.csv").write_text(HDR + "T,nope,,4,,,,,,Y,EXCHANGE,S14\n")
    args = ["validate-distributions", "--instruments", str(tmp_path / "i.csv"), "--file"]
    assert cli.main(args + [str(tmp_path / "good.csv")]) == 0
    assert cli.main(args + [str(tmp_path / "bad.csv")]) == 1


# ---- storage -------------------------------------------------------------------------------------------
@pytest.fixture()
def db():
    conn = storage.connect()
    storage.init_schema(conn)
    return conn


def test_schema_enforces_integrity(db):
    storage.save_instruments(db, [INVIT])
    with pytest.raises(sqlite3.IntegrityError):    # an included row must carry an amount
        db.execute("INSERT INTO distribution_event (event_id,instrument_key,ex_date,include_flag,amount_grade) "
                   "VALUES ('x','T','2026-01-01',1,'EXCHANGE')")
    with pytest.raises(sqlite3.IntegrityError):    # negative amount
        db.execute("INSERT INTO distribution_event (event_id,instrument_key,ex_date,total_per_unit,include_flag,amount_grade) "
                   "VALUES ('y','T','2026-01-01',-1,1,'EXCHANGE')")
    with pytest.raises(sqlite3.IntegrityError):    # unknown grade
        db.execute("INSERT INTO source (source_id,name,grade) VALUES ('s','n','HEARSAY')")
    with pytest.raises(sqlite3.IntegrityError):    # unknown instrument
        db.execute("INSERT INTO price_eod (instrument_key,trade_date,close) VALUES ('NOPE','2026-01-01',1)")
    with pytest.raises(sqlite3.IntegrityError):    # category only for ETFs
        db.execute("INSERT INTO instrument (instrument_key,name,type,etf_category) VALUES ('Q','q','INVIT','DEBT')")
    db.execute("INSERT INTO source (source_id,name,grade) VALUES ('s','n','EXCHANGE')")
    assert db.execute("SELECT display_cleared FROM source").fetchone() == (0,)      # licence gate defaults closed


def test_database_round_trip_reproduces_every_metric(bundle, as_of, db):
    storage.save_sources(db, bundle.sources.values())
    storage.save_instruments(db, bundle.instruments.values())
    storage.save_import_run(db, "run1", bundle.report, "2026-10-22T00:00:00Z")
    storage.save_events(db, bundle.events, "run1")
    db.commit()
    assert db.execute("SELECT COUNT(*) FROM distribution_event").fetchone()[0] == 398
    assert db.execute("SELECT COUNT(*) FROM import_issue").fetchone()[0] == len(bundle.report.issues)
    for key, inst in bundle.instruments.items():
        from_files = compute_all(Snapshot(inst, as_of, [e for e in bundle.events if e.instrument_key == key],
                                          bundle.prices.get(key), bundle.navs.get(key)))
        from_db = compute_all(Snapshot(inst, as_of, storage.load_events(db, key), bundle.prices.get(key),
                                       bundle.navs.get(key)))
        for n in from_files:
            a, b = from_files[n], from_db[n]
            assert (a.status, a.flags, a.reasons) == (b.status, b.flags, b.reasons), (key, n)
            assert a.value == b.value or abs(a.value - b.value) < D("1e-12"), (key, n)


# ---- publish gate ---------------------------------------------------------------------------------------
def make(flags=(), status=Status.OK, sids=("S14",)):
    return MetricResult("m", status, AS_OF, D(1) if status is Status.OK else None, flags=tuple(flags), source_ids=sids)


def test_publish_gate_defaults_closed_and_needs_clean_cleared_data():
    srcs = {"S14": Source("S14", "n", G.EXCHANGE)}
    ok_, why = publish_decision(make(), srcs)
    assert not ok_ and "source S14 not cleared for display" in why                  # nothing is cleared by default
    cleared = {"S14": Source("S14", "n", G.EXCHANGE, display_cleared=True)}
    assert publish_decision(make(), cleared)[0]
    for f in ("UNVERIFIED_SOURCE", "PRICE_STALE", "AMOUNT_UNAVAILABLE_IN_WINDOW", "COMPONENTS_DO_NOT_RECONCILE"):
        assert not publish_decision(make([f]), cleared)[0], f
    assert publish_decision(make(["NO_COMPONENT_SPLIT"]), cleared)[0]               # caveat flags do not block
    assert not publish_decision(make(status=Status.UNAVAILABLE), cleared)[0]
    assert not publish_decision(make(sids=("S99",)), cleared)[0]


def test_all_seed_sources_are_uncleared(bundle):
    assert bundle.sources and not any(s.display_cleared for s in bundle.sources.values())
