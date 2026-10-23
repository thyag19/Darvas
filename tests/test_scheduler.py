"""Market-hours scheduling with a fake clock: sessions, weekends, holidays, exceptional sessions, daily off-hours check,
missing calendar year, freshness, skip logging, and permission rules. No network; fetchers are fakes."""
import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from irie import freshness as fr, ingest, scheduler as sch, storage as st
from irie.market_calendar import IST, load_calendar, parse_calendar
from irie.models import SourceGrade as G
from irie.sources import Access, SourceSpec

ROOT = Path(__file__).resolve().parent.parent
EVID = {"status": "verified_official", "evidence_url": "https://example.test/circular", "checked_on": "2026-10-01"}
CAL = parse_calendar({
    "timezone": "Asia/Kolkata", "regular_session": {"open": "09:15", "close": "15:30", **EVID},
    "official_circulars": [{"number": "TEST/1", "date": "2025-12-12", "read": True}],
    "years": {"2026": {"holidays": [{"date": "2026-10-20", "name": "Dussehra", **EVID}, {"date": "2026-11-10", "name": "Diwali Balipratipada", **EVID}],
                       "holidays_complete": True,
                       "special_sessions": [{"date": "2026-11-08", "open": "18:00", "close": "18:50", **EVID},
                                            {"date": "2026-10-28", "closed": True, **EVID}]}}})


def ist(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=IST).astimezone(dt.timezone.utc)


def spec(**kw):
    base = dict(source_id="X", name="x", grade=G.EXCHANGE, kind="http", access=Access.CLEARED, clearance_evidence="test letter",
                terms_checked_on=dt.date(2026, 10, 1), schedule="market_and_daily", daily_time="19:00", min_interval_s=0,
                cadence_s=3600, max_staleness_s=7200)
    base.update(kw)
    return SourceSpec(**base)


class Recorder:
    """Fake fetcher: records every call (time, kinds) and returns nothing."""
    def __init__(self, clock):
        self.clock, self.calls = clock, []

    def fetch(self, spec, as_of, kinds=None):
        self.calls.append((self.clock(), kinds))
        return []


class Clock:
    def __init__(self):
        self.t = None

    def __call__(self):
        return self.t


@pytest.fixture()
def env():
    conn = st.connect(); st.init_schema(conn)
    clock = Clock()
    return conn, clock, Recorder(clock)


def run_day(env, sp, day, start=(0, 0), end=(23, 45), step=15, cal=CAL):
    conn, clock, rec = env
    t = ist(*day, *start)
    stop = ist(*day, *end)
    while t <= stop:
        clock.t = t
        ingest.run_cycle(conn, {sp.source_id: sp}, {sp.source_id: rec}, clock, calendar=cal, sleep=lambda s: None)
        t += dt.timedelta(minutes=step)


def attempts(rec, kinds_filter=None):
    return [(t.astimezone(IST), k) for t, k in rec.calls if kinds_filter is None or k == kinds_filter]


def test_trading_day_polls_hourly_only_inside_the_session(env):
    run_day(env, spec(), (2026, 10, 22))                       # Thursday
    market = attempts(env[2], sch.MARKET_KINDS)
    assert [t.strftime("%H:%M") for t, _ in market] == ["09:15", "10:15", "11:15", "12:15", "13:15", "14:15", "15:15"]
    assert all(dt.time(9, 15) <= t.time() <= dt.time(15, 30) for t, _ in market)
    daily = attempts(env[2], sch.DAILY_KINDS)
    assert [t.strftime("%H:%M") for t, _ in daily] == ["19:00"]                   # exactly once, off-hours
    assert len(env[2].calls) == 8                                            # nothing at any other time


def test_market_attempts_fetch_only_prices_and_daily_attempts_never_fetch_prices(env):
    run_day(env, spec(), (2026, 10, 22))
    for t, kinds in env[2].calls:
        if dt.time(9, 15) <= t.astimezone(IST).time() <= dt.time(15, 30):
            assert kinds == sch.MARKET_KINDS
        else:
            assert kinds == sch.DAILY_KINDS and "prices" not in kinds


@pytest.mark.parametrize("day,why", [((2026, 10, 20), "HOLIDAY"), ((2026, 10, 24), "WEEKEND"), ((2026, 10, 25), "WEEKEND")])
def test_holidays_and_weekends_have_no_price_polling_but_the_daily_check_still_runs(env, day, why):
    run_day(env, spec(), day)
    assert attempts(env[2], sch.MARKET_KINDS) == []
    assert len(attempts(env[2], sch.DAILY_KINDS)) == 1
    note = env[0].execute("SELECT note FROM retrieval_log WHERE status='SKIPPED_OUTSIDE_SESSION' ORDER BY started_at LIMIT 1").fetchone()[0]
    assert note.startswith(f"OUTSIDE_SESSION: {why}" if why != "HOLIDAY" else "OUTSIDE_SESSION: HOLIDAY: Dussehra")


def test_exceptional_sessions_are_honoured_both_ways(env):
    run_day(env, spec(), (2026, 11, 8), step=15)                # Sunday with a configured evening session 18:00-18:50
    m = attempts(env[2], sch.MARKET_KINDS)
    assert [t.strftime("%H:%M") for t, _ in m] == ["18:00"]
    run_day(env, spec(), (2026, 10, 28), step=15)               # a weekday configured as closed
    assert [t for t, _ in attempts(env[2], sch.MARKET_KINDS) if t.date() == dt.date(2026, 10, 28)] == []


def test_a_year_missing_from_the_calendar_fails_closed(env):
    run_day(env, spec(), (2027, 1, 4))                          # Monday, calendar has only 2026
    assert attempts(env[2], sch.MARKET_KINDS) == []
    note = env[0].execute("SELECT note FROM retrieval_log WHERE status='SKIPPED_OUTSIDE_SESSION' LIMIT 1").fetchone()[0]
    assert "CALENDAR_NOT_LOADED" in note


def test_daily_time_inside_the_session_is_rejected():
    with pytest.raises(ValueError, match="inside the trading session"):
        sch.validate_schedule(spec(daily_time="12:00"), CAL)
    sch.validate_schedule(spec(daily_time="19:00"), CAL)


def test_skips_never_reset_the_cadence_and_force_cannot_override_session_rules(env):
    conn, clock, rec = env
    sp = spec()
    clock.t = ist(2026, 10, 22, 8, 0)
    ingest.run_cycle(conn, {"X": sp}, {"X": rec}, clock, calendar=CAL, sleep=lambda s: None, force=True)
    assert rec.calls == []                                      # force does not make a closed market pollable
    clock.t = ist(2026, 10, 22, 9, 16)
    ingest.run_cycle(conn, {"X": sp}, {"X": rec}, clock, calendar=CAL, sleep=lambda s: None)
    assert len(rec.calls) == 1                                  # first tick of the session is due despite earlier skips


def test_skip_rows_are_logged_at_most_hourly_per_reason(env):
    run_day(env, spec(), (2026, 10, 24))                        # Saturday, 15-minute ticks all day
    n = env[0].execute("SELECT COUNT(*) FROM retrieval_log WHERE status='SKIPPED_OUTSIDE_SESSION'").fetchone()[0]
    assert 20 <= n <= 25                                        # ~24 hourly rows, not 96


def test_log_rows_carry_window_class_and_note(env):
    run_day(env, spec(), (2026, 10, 22), start=(9, 0), end=(9, 30))
    rows = env[0].execute("SELECT status, window_class FROM retrieval_log ORDER BY started_at, rowid").fetchall()
    assert ("SKIPPED_OUTSIDE_SESSION", "market") in rows and ("NO_NEW_DATA", "market") in rows


def test_not_cleared_sources_are_never_attempted_even_in_session(env):
    run_day(env, spec(access=Access.NOT_CLEARED, clearance_evidence=""), (2026, 10, 22))
    assert env[2].calls == []
    assert {r[0] for r in env[0].execute("SELECT DISTINCT status FROM retrieval_log")} == {"SKIPPED_NOT_CLEARED"}


def test_market_schedule_without_a_calendar_is_an_error(env):
    conn, clock, rec = env
    clock.t = ist(2026, 10, 22, 10)
    with pytest.raises(ValueError, match="needs a market calendar"):
        ingest.run_cycle(conn, {"X": spec()}, {"X": rec}, clock, sleep=lambda s: None)


def test_local_schedule_reads_files_on_cadence_not_on_market_hours(env):
    sp = spec(kind="file_inbox", access=Access.USER_SUPPLIED, schedule="local", clearance_evidence="")
    run_day(env, sp, (2026, 10, 24), step=30)                   # a Saturday: still hourly, nothing external is contacted
    assert len(env[2].calls) == 24


def test_daily_runs_once_per_ist_date_across_days(env):
    sp = spec(schedule="daily")
    run_day(env, sp, (2026, 10, 22))
    run_day(env, sp, (2026, 10, 23))
    assert [t.date().isoformat() for t, _ in attempts(env[2])] == ["2026-10-22", "2026-10-23"]
    assert all(t.strftime("%H:%M") == "19:00" for t, _ in attempts(env[2]))


# ---- market-hours attempts only ingest permitted kinds -------------------------------------------------------------
def test_price_files_are_not_ingested_outside_a_session_and_distributions_wait_for_the_daily_check(tmp_path):
    conn = st.connect(); st.init_schema(conn)
    d = tmp_path / "X"; d.mkdir()
    (d / "instruments_a.csv").write_text("key,name,type\nI1,Inst,INVIT\n")
    (d / "prices_a.csv").write_text("instrument_key,date,price,venue\nI1,2026-10-22,100,NSE\n")
    (d / "distributions_a.csv").write_text("instrument_key,ex_date,total_per_unit,amount_grade\nI1,2026-08-01,3,EXCHANGE\n")
    clock = Clock()
    f = ingest.FileInboxFetcher(tmp_path, clock)
    sp = spec()
    count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    clock.t = ist(2026, 10, 22, 10)                             # in session: prices only (instruments are a daily kind)
    ingest.run_cycle(conn, {"X": sp}, {"X": f}, clock, calendar=CAL, sleep=lambda s: None)
    assert count("price_eod") == 0 and count("distribution_event") == 0     # price file refused: unknown instrument yet
    clock.t = ist(2026, 10, 22, 19, 5)                          # daily check: instruments + distributions, not prices
    ingest.run_cycle(conn, {"X": sp}, {"X": f}, clock, calendar=CAL, sleep=lambda s: None)
    assert count("instrument") == 1 and count("distribution_event") == 1 and count("price_eod") == 0
    clock.t = ist(2026, 10, 23, 9, 20)                          # next session: prices flow
    ingest.run_cycle(conn, {"X": sp}, {"X": f}, clock, calendar=CAL, sleep=lambda s: None)
    assert count("price_eod") == 1


# ---- freshness against the schedule --------------------------------------------------------------------------------
def test_freshness_is_judged_against_the_last_close_over_a_weekend_and_stale_on_monday():
    sp = spec(schedule="market_hours")
    ok = fr.utc_iso(ist(2026, 10, 23, 15, 17))                  # Friday last attempt
    assert fr.classify(sp, ok, ist(2026, 10, 24, 12), CAL) is fr.Freshness.FRESH      # Saturday
    assert fr.classify(sp, ok, ist(2026, 10, 26, 8, 0), CAL) is fr.Freshness.FRESH    # Monday before open
    assert fr.classify(sp, ok, ist(2026, 10, 26, 12, 0), CAL) is fr.Freshness.STALE   # in session, nothing since Friday
    assert fr.classify(sp, None, ist(2026, 10, 26, 12), CAL) is fr.Freshness.NEVER
    assert fr.classify(spec(access=Access.NOT_CLEARED, clearance_evidence=""), ok, ist(2026, 10, 26, 12), CAL) is fr.Freshness.NOT_FETCHED


def test_daily_freshness_uses_the_latest_slot():
    sp = spec(schedule="daily", max_staleness_s=93600)
    yday = fr.utc_iso(ist(2026, 10, 22, 19, 1))
    assert fr.classify(sp, yday, ist(2026, 10, 23, 18, 0), CAL) is fr.Freshness.FRESH   # today's slot has not arrived
    assert fr.classify(sp, yday, ist(2026, 10, 25, 20, 0), CAL) is fr.Freshness.STALE   # two daily slots missed


def test_next_attempt_hints():
    sp = spec(schedule="market_hours")
    sat = sch.next_attempt(sp, CAL, ist(2026, 10, 24, 12), {})
    assert sat.astimezone(IST) == dt.datetime(2026, 10, 26, 9, 15, tzinfo=IST)           # Monday open
    mid = sch.next_attempt(sp, CAL, ist(2026, 10, 22, 11, 30), {"market": fr.utc_iso(ist(2026, 10, 22, 11, 15))})
    assert mid.astimezone(IST) == dt.datetime(2026, 10, 22, 12, 15, tzinfo=IST)
    late = sch.next_attempt(sp, CAL, ist(2026, 10, 22, 15, 20), {"market": fr.utc_iso(ist(2026, 10, 22, 15, 15))})
    assert late.astimezone(IST) == dt.datetime(2026, 10, 23, 9, 15, tzinfo=IST)         # no more attempts today
    dly = sch.next_attempt(spec(schedule="daily"), CAL, ist(2026, 10, 22, 12), {})
    assert dly.astimezone(IST) == dt.datetime(2026, 10, 22, 19, 0, tzinfo=IST)


def test_shipped_calendar_is_flagged_unverified_and_knows_the_dussehra_closure():
    cal = load_calendar(ROOT / "config" / "market_calendar.json")
    assert not cal.verified and cal.covers(dt.date(2026, 10, 22)) and not cal.covers(dt.date(2027, 1, 4))
    assert cal.status(ist(2026, 10, 20, 11)).reason == "HOLIDAY"
    assert cal.status(ist(2026, 10, 22, 11)).open and not cal.status(ist(2026, 10, 22, 15, 31)).open
    assert cal.status(ist(2026, 10, 22, 9, 14)).reason == "BEFORE_OPEN" and cal.status(ist(2026, 10, 22, 9, 15)).open


def test_shipped_registry_schedules_validate_against_the_shipped_calendar():
    from irie.sources import load_registry
    cal, reg = load_calendar(ROOT / "config" / "market_calendar.json"), load_registry(ROOT / "config" / "sources.json")
    for s in reg.values():
        sch.validate_schedule(s, cal)
    assert reg["INBOX"].schedule == "local" and reg["NSE"].schedule == "market_and_daily" and reg["AMFI"].schedule == "daily"
