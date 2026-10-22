"""NAV-relative and leverage helpers for REIT and InvIT (fair-value NAV, reported leverage)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from ..models import LeveragePoint, NavPoint, PricePoint, VERIFIED_GRADES
from ..result import MetricResult, Status, ok, withheld
from .common import DEFAULT_NAV_STALE_DAYS, check_nav, check_price


def premium_to_nav(price: Optional[PricePoint], nav: Optional[NavPoint], as_of: dt.date, *,
                   price_stale_days: int = 3, nav_stale_days: int = DEFAULT_NAV_STALE_DAYS,
                   name: str = "premium_to_nav") -> MetricResult:
    """price / NAV - 1 with the NAV date shown. Positive = premium. NAV is a periodic fair-value NAV, so a
    stale NAV is flagged, not hidden."""
    px, pr, pf = check_price(price, as_of, price_stale_days)
    nv, nr, nf = check_nav(nav, as_of, nav_stale_days)
    if px is None or nv is None:
        return withheld(name, as_of, Status.UNAVAILABLE, pr + nr, "ratio", pf + nf)
    sid = {s for s in (price.source_id, nav.source_id) if s}
    return ok(name, as_of, px / nv - 1, "ratio", pf + nf, sid,
              [("price", str(px)), ("nav", str(nv)), ("nav_date", nav.nav_date.isoformat())])


def net_debt_to_gav(net_debt: Optional[Decimal], gav: Optional[Decimal], as_of: dt.date,
                    source_id: str = "", verified: bool = False) -> MetricResult:
    """REIT loan-to-value as net debt / gross asset value. Both inputs must come from the same filing and
    date. Net debt may legitimately be negative (net cash); GAV must be positive."""
    if net_debt is None or gav is None:
        return withheld("net_debt_to_gav", as_of, Status.UNAVAILABLE, ["INPUT_MISSING"], "ratio")
    if gav <= 0:
        return withheld("net_debt_to_gav", as_of, Status.UNAVAILABLE, ["GAV_NOT_POSITIVE"], "ratio")
    return ok("net_debt_to_gav", as_of, net_debt / gav, "ratio", [] if verified else ["LEVERAGE_UNVERIFIED"],
              {source_id} if source_id else (), [("net_debt", str(net_debt)), ("gav", str(gav))])


def reported_leverage(point: Optional[LeveragePoint], as_of: dt.date) -> MetricResult:
    """Pass a disclosed leverage figure through together with its definition. Definitions differ across
    issuers (see LeverageDefinition), so values must not be compared across instruments."""
    if point is None:
        return withheld("reported_leverage", as_of, Status.UNAVAILABLE, ["LEVERAGE_NOT_SUPPLIED"], "ratio")
    if point.date > as_of:
        return withheld("reported_leverage", as_of, Status.UNAVAILABLE, ["LEVERAGE_AFTER_AS_OF"], "ratio")
    flags = [] if point.grade in VERIFIED_GRADES else ["LEVERAGE_UNVERIFIED"]
    return ok("reported_leverage", as_of, point.value, "ratio", flags + ["DEFINITION_" + point.definition.value],
              {point.source_id} if point.source_id else (),
              [("definition", point.definition.value), ("as_of_date", point.date.isoformat())])
