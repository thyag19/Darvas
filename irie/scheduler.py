"""When may a source be attempted? Market-data refreshes run hourly during NSE/BSE trading sessions only (Asia/Kolkata,
weekends, exchange holidays and exceptional sessions from the calendar). Non-price material (announcements,
distributions, NAV, leverage, holdings) may be checked once a day at a configurable off-hours time. Nothing is
polled for market prices outside a session. A year missing from the calendar fails closed (no market polling).

Schedules (SourceSpec.schedule):
  local            local files (inbox) on the plain cadence; no external server is contacted
  market_hours     prices, hourly during sessions
  daily            non-price kinds, once per IST day after daily_time
  market_and_daily both of the above
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import FrozenSet, Optional

from .freshness import parse_utc
from .market_calendar import IST, MarketCalendar
from .sources import SourceSpec

MARKET_KINDS: FrozenSet[str] = frozenset({"prices"})
DAILY_KINDS: FrozenSet[str] = frozenset({"instruments", "distributions", "navs", "leverage", "news", "holdings"})
SLACK_S = 120


@dataclass(frozen=True)
class Decision:
    due: bool
    reason: str                              # MARKET_SESSION | DAILY_CHECK | LOCAL_CADENCE | skip reasons below
    kinds: Optional[FrozenSet[str]] = None   # which data kinds this attempt may fetch (None = all, local files)
    window_class: str = "local"              # 'market' | 'daily' | 'local' (what an attempt counts against)
    note: str = ""


def daily_slot(spec: SourceSpec, d: dt.date) -> dt.datetime:
    h, m = spec.daily_time.split(":")
    return dt.datetime.combine(d, dt.time(int(h), int(m)), tzinfo=IST)


def validate_schedule(spec: SourceSpec, cal: MarketCalendar) -> None:
    if "daily" in spec.schedule or spec.schedule == "daily":
        h, m = spec.daily_time.split(":")
        t = dt.time(int(h), int(m))
        if cal.regular[0] <= t <= cal.regular[1]:
            raise ValueError(f"{spec.source_id}: daily_time {spec.daily_time} falls inside the trading session; "
                             "the daily check must be off-hours")


def _market(spec, cal, now, last_market: Optional[str]) -> Decision:
    st = cal.status(now)
    if not st.calendar_loaded:
        return Decision(False, "CALENDAR_NOT_LOADED", None, "market", f"no calendar for {now.astimezone(IST).year}; not polling")
    if not st.open:
        return Decision(False, "OUTSIDE_SESSION", None, "market",
                        st.reason + (f": {st.holiday_name}" if st.holiday_name else ""))
    opened = cal.session_bounds(now.astimezone(IST).date())[0]
    last = parse_utc(last_market) if last_market else None
    if last is None or last < opened or (now - last).total_seconds() >= spec.cadence_s - SLACK_S:
        return Decision(True, "MARKET_SESSION", MARKET_KINDS, "market", "unverified calendar" if not st.verified else "")
    return Decision(False, "NOT_DUE", None, "market", "already refreshed this hour")


def _daily(spec, now, last_daily: Optional[str]) -> Decision:
    n = now.astimezone(IST)
    slot = daily_slot(spec, n.date())
    if n < slot:
        return Decision(False, "NOT_YET_TIME", None, "daily", f"daily check at {spec.daily_time} IST")
    last = parse_utc(last_daily) if last_daily else None
    if last is None or last < slot:
        return Decision(True, "DAILY_CHECK", DAILY_KINDS, "daily")
    return Decision(False, "NOT_DUE", None, "daily", "already checked today")


def decide(spec: SourceSpec, cal: Optional[MarketCalendar], now: dt.datetime, last_by_class: dict) -> Decision:
    """last_by_class: {'market'|'daily'|'local': UTC ISO of the last real attempt of that class}."""
    if spec.schedule == "local":
        last = last_by_class.get("local")
        due = last is None or (now - parse_utc(last)).total_seconds() >= spec.cadence_s - SLACK_S
        return Decision(due, "LOCAL_CADENCE" if due else "NOT_DUE", None, "local")
    if cal is None:
        raise ValueError(f"{spec.source_id}: schedule {spec.schedule!r} needs a market calendar")
    decisions = []
    if spec.schedule in ("market_hours", "market_and_daily"):
        decisions.append(_market(spec, cal, now, last_by_class.get("market")))
    if spec.schedule in ("daily", "market_and_daily"):
        decisions.append(_daily(spec, now, last_by_class.get("daily")))
    due = [d for d in decisions if d.due]
    if due:
        return due[0]
    return decisions[0]


def next_attempt(spec: SourceSpec, cal: Optional[MarketCalendar], now: dt.datetime, last_by_class: dict) -> Optional[dt.datetime]:
    """Best-effort time of the next scheduled attempt (for display)."""
    if spec.schedule == "local" or cal is None:
        last = last_by_class.get("local")
        return now if last is None else parse_utc(last) + dt.timedelta(seconds=spec.cadence_s)
    cands = []
    if spec.schedule in ("market_hours", "market_and_daily") and cal.covers(now.astimezone(IST).date()):
        if cal.is_open(now):
            last = last_by_class.get("market")
            nxt = now if not last else max(now, parse_utc(last) + dt.timedelta(seconds=spec.cadence_s))
            close = cal.session_bounds(now.astimezone(IST).date())[1]
            if nxt <= close:
                cands.append(nxt)
        if not cands:
            no = cal.next_open(now)
            if no:
                cands.append(no)
    if spec.schedule in ("daily", "market_and_daily"):
        n = now.astimezone(IST)
        for ahead in range(3):
            slot = daily_slot(spec, n.date() + dt.timedelta(days=ahead))
            last = last_by_class.get("daily")
            if slot > now or (ahead == 0 and (not last or parse_utc(last) < slot)):
                cands.append(max(slot, now) if ahead == 0 else slot)
                break
    return min(cands) if cands else None
