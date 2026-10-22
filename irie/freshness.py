"""Freshness tracking. Retrieval time (when we fetched) is never confused with observation time (when the market
or issuer produced the value): a source can be fetched every hour and still be serving yesterday's close."""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass
from typing import Optional

from .market_calendar import IST
from .sources import SourceSpec


class Freshness(str, enum.Enum):
    FRESH = "FRESH"          # a good retrieval within max_staleness_s
    STALE = "STALE"          # last good retrieval is older than max_staleness_s
    NEVER = "NEVER"          # no good retrieval on record
    NOT_FETCHED = "NOT_FETCHED"   # source is not cleared/enabled; by design nothing is retrieved


@dataclass(frozen=True)
class SourceStatus:
    source_id: str
    freshness: Freshness
    last_attempt_at: Optional[str]
    last_attempt_status: Optional[str]
    last_success_at: Optional[str]
    observed_through: Optional[str]
    consecutive_failures: int
    next_attempt_at: Optional[str] = None
    schedule: str = "local"


def parse_utc(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def utc_iso(t: dt.datetime) -> str:
    if t.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reference_time(spec: SourceSpec, cal, now: dt.datetime) -> dt.datetime:
    """The moment a good retrieval should at least have covered. Market-hours sources are judged against the last close
    when the market is shut (a Friday-close retrieval is fresh all weekend); daily sources against the latest daily slot."""
    refs = []
    if spec.schedule in ("market_hours", "market_and_daily") and cal is not None:
        refs.append(now if cal.is_open(now) else (cal.last_close(now) or now))
    if spec.schedule in ("daily", "market_and_daily"):
        from .scheduler import daily_slot
        n = now.astimezone(IST)
        slot = daily_slot(spec, n.date())
        refs.append(slot if slot <= now else daily_slot(spec, n.date() - dt.timedelta(days=1)))
    return max(refs) if refs else now


def classify(spec: SourceSpec, last_success_at: Optional[str], now: dt.datetime, cal=None) -> Freshness:
    if not spec.may_fetch:
        return Freshness.NOT_FETCHED
    if last_success_at is None:
        return Freshness.NEVER
    ref = reference_time(spec, cal, now)
    return Freshness.FRESH if (ref - parse_utc(last_success_at)).total_seconds() <= spec.max_staleness_s else Freshness.STALE


def is_due(spec: SourceSpec, last_attempt_at: Optional[str], now: dt.datetime, slack_s: int = 120) -> bool:
    """Attempt every cadence_s (hourly), with slack so a scheduler that fires a little early is not skipped."""
    return last_attempt_at is None or (now - parse_utc(last_attempt_at)).total_seconds() >= spec.cadence_s - slack_s


def ist_date(now: dt.datetime) -> dt.date:
    """Market dates are IST. Convert an aware UTC timestamp to the IST calendar date."""
    return now.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
