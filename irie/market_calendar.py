"""NSE/BSE trading calendar in Asia/Kolkata: regular session, weekends, exchange holidays, exceptional sessions.

Nothing here knows about any particular data source. The scheduler asks "is the market open?" and "when was the last
close?". Years that are not in the calendar file are NOT assumed to be ordinary weekdays silently: `covers(date)` is False
and callers flag the decision as CALENDAR_NOT_LOADED. A calendar with verified=false says so in every status it returns.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:  # pragma: no cover - tzdata missing: India has no DST, so a fixed offset is exact
    IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")

Window = Tuple[dt.time, dt.time]


@dataclass(frozen=True)
class MarketStatus:
    open: bool
    reason: str            # OPEN | BEFORE_OPEN | AFTER_CLOSE | WEEKEND | HOLIDAY | SPECIAL_SESSION | NO_SESSION
    holiday_name: str = ""
    calendar_loaded: bool = True
    verified: bool = False


@dataclass
class MarketCalendar:
    regular: Window = (dt.time(9, 15), dt.time(15, 30))
    holidays: Dict[dt.date, str] = field(default_factory=dict)
    special: Dict[dt.date, Optional[Window]] = field(default_factory=dict)   # None = exceptional full closure
    years: frozenset = frozenset()
    verified: bool = False

    def covers(self, d: dt.date) -> bool:
        return d.year in self.years

    def window(self, d: dt.date) -> Optional[Window]:
        """Trading window for a calendar date, or None if the exchange is closed that day."""
        if d in self.special:
            return self.special[d]
        if d.weekday() >= 5 or d in self.holidays:
            return None
        return self.regular

    def _dt(self, d: dt.date, t: dt.time) -> dt.datetime:
        return dt.datetime.combine(d, t, tzinfo=IST)

    def status(self, now: dt.datetime) -> MarketStatus:
        n = now.astimezone(IST)
        d, w = n.date(), self.window(n.date())
        base = dict(calendar_loaded=self.covers(d), verified=self.verified)
        if w is None:
            if d in self.holidays:
                return MarketStatus(False, "HOLIDAY", self.holidays[d], **base)
            return MarketStatus(False, "WEEKEND" if d.weekday() >= 5 else "NO_SESSION", **base)
        o, c = self._dt(d, w[0]), self._dt(d, w[1])
        special = d in self.special
        if n < o:
            return MarketStatus(False, "BEFORE_OPEN", **base)
        if n > c:
            return MarketStatus(False, "AFTER_CLOSE", **base)
        return MarketStatus(True, "SPECIAL_SESSION" if special else "OPEN", **base)

    def is_open(self, now: dt.datetime) -> bool:
        return self.status(now).open

    def session_bounds(self, d: dt.date) -> Optional[Tuple[dt.datetime, dt.datetime]]:
        w = self.window(d)
        return None if w is None else (self._dt(d, w[0]), self._dt(d, w[1]))

    def last_close(self, now: dt.datetime) -> Optional[dt.datetime]:
        """Most recent session close at or before now (looks back up to 14 days)."""
        n = now.astimezone(IST)
        for back in range(15):
            b = self.session_bounds(n.date() - dt.timedelta(days=back))
            if b and b[1] <= n:
                return b[1]
        return None

    def next_open(self, now: dt.datetime) -> Optional[dt.datetime]:
        n = now.astimezone(IST)
        for ahead in range(15):
            b = self.session_bounds(n.date() + dt.timedelta(days=ahead))
            if b and b[0] > n:
                return b[0]
        return None


def _t(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def parse_calendar(obj: dict) -> MarketCalendar:
    if obj.get("timezone", "Asia/Kolkata") != "Asia/Kolkata":
        raise ValueError("only Asia/Kolkata is supported")
    reg = obj.get("regular_session", {"open": "09:15", "close": "15:30"})
    cal = MarketCalendar(regular=(_t(reg["open"]), _t(reg["close"])), verified=bool(obj.get("verified", False)))
    if cal.regular[0] >= cal.regular[1]:
        raise ValueError("regular session must open before it closes")
    years = set()
    for y, body in obj.get("years", {}).items():
        years.add(int(y))
        for h in body.get("holidays", []):
            cal.holidays[dt.date.fromisoformat(h["date"])] = h.get("name", "")
        for s in body.get("special_sessions", []):
            d = dt.date.fromisoformat(s["date"])
            cal.special[d] = None if s.get("closed") else (_t(s["open"]), _t(s["close"]))
    cal.years = frozenset(years)
    return cal


def load_calendar(path) -> MarketCalendar:
    return parse_calendar(json.loads(Path(path).read_text(encoding="utf-8")))
