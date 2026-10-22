"""Input checks shared by the instrument modules: dates must be explicit and consistent."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from ..models import NavPoint, PricePoint, VERIFIED_GRADES

DEFAULT_PRICE_STALE_DAYS = 3        # workbook StaleDays
DEFAULT_NAV_STALE_DAYS = 270        # workbook rule for annual/semi-annual valuations (assumption, configurable)
TTM_DAYS = 365


def ttm_window(as_of: dt.date):
    """(start_exclusive, end_inclusive] for the trailing 12 months, ex-date based (workbook definition)."""
    return as_of - dt.timedelta(days=TTM_DAYS), as_of


def prior_window(as_of: dt.date):
    return as_of - dt.timedelta(days=2 * TTM_DAYS), as_of - dt.timedelta(days=TTM_DAYS)


def check_price(price: Optional[PricePoint], as_of: dt.date, stale_days: int = DEFAULT_PRICE_STALE_DAYS):
    """Return (price_or_None, reasons, flags). A price dated after as_of is rejected, not used."""
    if price is None:
        return None, ["PRICE_MISSING"], []
    if price.price is None or price.price <= 0:
        return None, ["PRICE_NOT_POSITIVE"], []
    if price.date > as_of:
        return None, [f"PRICE_AFTER_AS_OF ({price.date.isoformat()} > {as_of.isoformat()})"], []
    flags = ["PRICE_STALE"] if (as_of - price.date).days > stale_days else []
    return price.price, [], flags


def check_nav(nav: Optional[NavPoint], as_of: dt.date, stale_days: int = DEFAULT_NAV_STALE_DAYS):
    if nav is None:
        return None, ["NAV_MISSING"], []
    if nav.nav is None or nav.nav <= 0:
        return None, ["NAV_NOT_POSITIVE"], []
    if nav.nav_date > as_of:
        return None, [f"NAV_AFTER_AS_OF ({nav.nav_date.isoformat()} > {as_of.isoformat()})"], []
    flags = []
    if (as_of - nav.nav_date).days > stale_days:
        flags.append("NAV_STALE")
    if nav.grade not in VERIFIED_GRADES:
        flags.append("NAV_UNVERIFIED")
    return nav.nav, [], flags


def as_of_consistency(as_of: dt.date, dated_inputs: dict, max_future_days: int = 0):
    """Report inputs dated after the report date (the workbook mixed 21-Oct and 22-Oct observations).
    dated_inputs: {label: date}. Returns a list of human-readable issues."""
    return [f"{label} dated {d.isoformat()} is after as_of {as_of.isoformat()}"
            for label, d in sorted(dated_inputs.items()) if d is not None and (d - as_of).days > max_future_days]
