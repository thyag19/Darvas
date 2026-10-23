"""Calendar verification status: nothing is called verified without evidence; unconfirmed exceptional sessions fail closed."""
import datetime as dt
import json
from pathlib import Path

import pytest

from irie import ingest, scheduler as sch, storage as st
from irie.market_calendar import IST, load_calendar, parse_calendar
from tests.test_scheduler import CAL, Clock, Recorder, attempts, ist, run_day, spec

ROOT = Path(__file__).resolve().parent.parent
EVID = {"status": "verified_official", "evidence_url": "https://example.test/c", "checked_on": "2026-10-01"}
READ = [{"number": "T/1", "date": "2025-12-12", "read": True}]


def cal(**kw):
    obj = {"regular_session": {"open": "09:15", "close": "15:30"}, "official_circulars": READ, "years": {"2026": {"holidays": [{"date": "2026-10-20", "name": "x"}]}}}
    obj.update(kw)
    return obj


def test_a_date_cannot_be_marked_verified_without_evidence_or_a_circular_that_was_read():
    h = lambda **e: cal(years={"2026": {"holidays": [{"date": "2026-10-20", "name": "x", "status": "verified_official", **e}]}})
    with pytest.raises(ValueError, match="needs evidence_url"):
        parse_calendar(h())                                                          # no evidence at all
    with pytest.raises(ValueError, match="needs evidence_url"):
        parse_calendar(h(evidence_url="https://e.test"))                             # no check date
    with pytest.raises(ValueError, match="read=true"):
        parse_calendar({**h(evidence_url="https://e.test", checked_on="2026-10-01"),
                        "official_circulars": [{"number": "T/1", "date": "x", "read": False}]})   # circular identified but not read
    ok = parse_calendar(h(evidence_url="https://e.test", checked_on="2026-10-01"))
    assert ok.holiday_status[dt.date(2026, 10, 20)] == "verified_official"
    with pytest.raises(ValueError, match="unknown status"):
        parse_calendar(cal(years={"2026": {"holidays": [{"date": "2026-10-20", "status": "probably"}]}}))


def test_calendar_is_verified_only_when_everything_is():
    c = parse_calendar(cal())
    assert not c.verified                                                            # default status: unverified_secondary
    full = cal(regular_session={"open": "09:15", "close": "15:30", **EVID},
               years={"2026": {"holidays": [{"date": "2026-10-20", "name": "x", **EVID}], "holidays_complete": True}})
    assert parse_calendar(full).verified
    no_complete = json.loads(json.dumps(full)); no_complete["years"]["2026"]["holidays_complete"] = False
    assert not parse_calendar(no_complete).verified                                  # list not asserted complete from the circular
    mixed = json.loads(json.dumps(full)); mixed["years"]["2026"]["holidays"].append({"date": "2026-11-10", "name": "y"})
    mixed["years"]["2026"]["holidays_complete"] = False
    assert not parse_calendar(mixed).verified
    with pytest.raises(ValueError, match="holidays_complete requires"):
        bad = json.loads(json.dumps(mixed)); bad["years"]["2026"]["holidays_complete"] = True; parse_calendar(bad)
    pend = json.loads(json.dumps(full)); pend["years"]["2026"]["pending_sessions"] = [{"date": "2026-11-08", "note": "times unconfirmed"}]
    assert not parse_calendar(pend).verified                                         # an unconfirmed exceptional session blocks "verified"


def test_special_sessions_must_themselves_be_verified_else_they_belong_in_pending():
    with pytest.raises(ValueError, match="pending_sessions"):
        parse_calendar(cal(years={"2026": {"holidays": [], "special_sessions": [{"date": "2026-11-08", "open": "14:20", "close": "15:30"}]}}))


def test_pending_session_fails_closed_but_the_daily_check_still_runs(tmp_path):
    c = parse_calendar(cal(years={"2026": {"holidays": [], "pending_sessions": [{"date": "2026-11-08", "note": "Muhurat times not confirmed"}]}}))
    assert c.status(ist(2026, 11, 8, 14, 30)).reason == "SPECIAL_SESSION_UNVERIFIED" and not c.is_open(ist(2026, 11, 8, 14, 30))
    conn = st.connect(); st.init_schema(conn)
    clk = Clock(); rec = Recorder(clk)
    for t in range(0, 24 * 4):
        clk.t = ist(2026, 11, 8, 0, 0) + dt.timedelta(minutes=15 * t)
        ingest.run_cycle(conn, {"X": spec()}, {"X": rec}, clk, calendar=c, sleep=lambda s: None)
    assert [k for _, k in rec.calls] == [sch.DAILY_KINDS]                           # no price polling at all that Sunday; one daily check
    note = conn.execute("SELECT note FROM retrieval_log WHERE status='SKIPPED_OUTSIDE_SESSION' LIMIT 1").fetchone()[0]
    assert "SPECIAL_SESSION_UNVERIFIED" in note


def test_the_shipped_calendar_claims_no_official_verification_and_fails_closed():
    c = load_calendar(ROOT / "config" / "market_calendar.json")
    raw = json.loads((ROOT / "config" / "market_calendar.json").read_text())
    assert not c.verified and c.regular_status == "unverified_secondary"
    v = c.verification()
    assert v["holidays_verified"] == 0 and v["holidays_total"] == 16 and v["disputed"] == ["2026-01-15"] and v["years_complete"] == []
    assert [p["date"] for p in v["pending_sessions"]] == ["2026-11-08"]
    assert all(not x["read"] for x in v["official_circulars"]) and {x["number"] for x in v["official_circulars"]} >= {"NSE/CMTR/71775", "NSE/CMTR/76941"}
    assert all(h["status"] != "verified_official" for h in raw["years"]["2026"]["holidays"])
    assert not c.is_open(ist(2026, 11, 8, 14, 30))                                   # Muhurat times are not used until officially confirmed
    assert c.status(ist(2026, 11, 10, 11)).reason == "HOLIDAY" and c.status(ist(2026, 12, 25, 11)).reason == "HOLIDAY"
    assert c.status(ist(2026, 10, 23, 11)).open and c.status(ist(2026, 10, 20, 11)).reason == "HOLIDAY"
    assert not c.covers(dt.date(2027, 1, 4))                                          # 2027 is not loaded: market polling fails closed


def test_year_end_and_leap_boundaries_and_dst_free_ist_offsets():
    assert ist(2026, 12, 31, 15, 30).astimezone(dt.timezone.utc) == dt.datetime(2026, 12, 31, 10, 0, tzinfo=dt.timezone.utc)
    assert CAL.status(ist(2026, 12, 31, 15, 31)).reason in ("AFTER_CLOSE", "NO_SESSION", "WEEKEND", "HOLIDAY")
    assert not CAL.status(dt.datetime(2027, 1, 1, 5, 0, tzinfo=dt.timezone.utc)).calendar_loaded     # first minute of an unloaded year
    # 20:00 UTC on 31 Dec 2026 is already 01:30 IST on 1 Jan 2027: IST decides the market date, so 2027 (not loaded) applies
    assert not CAL.status(dt.datetime(2026, 12, 31, 20, 0, tzinfo=dt.timezone.utc)).calendar_loaded


def test_dataset_exposes_the_verification_summary(tmp_path):
    from irie import demo, export
    conn = st.connect(); st.init_schema(conn)
    c = load_calendar(ROOT / "config" / "market_calendar.json")
    m = export.build_dataset(conn, demo.demo_registry(), demo.DEMO_NOW, "public", c)["market"]
    assert m["calendar_verified"] is False and m["verification"]["holidays_verified"] == 0 and m["verification"]["pending_sessions"]
