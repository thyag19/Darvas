"""ETF metrics. ETFs are NOT given a distribution yield by default: most do not distribute, and an index's
dividend yield is not a fund yield. Metrics are defined per category in irie.registry.

Methodology:
  premium_discount      price / NAV - 1 on the SAME date (default zero-day tolerance).
  nav_return            NAV_end / NAV_start - 1 using the last NAV on or before each target date, provided it
                        is within max_gap_days. Annualised (CAGR) only for spans >= 365 days. It EXCLUDES any
                        distributions, so for a distributing scheme it is flagged and is not a total return.
  tracking_difference   fund nav_return - benchmark return over the same window, same date rules. It is
                        cumulative return difference, not tracking error (which needs a daily series and is
                        deliberately out of M1). Benchmark levels must be supplied by the caller; their
                        licensing is not cleared.
  trailing_distribution_yield   defined only when the scheme is known to distribute; no component split.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional, Sequence

from ..models import DistributionEvent, Instrument, NavPoint, PricePoint, VERIFIED_GRADES
from ..result import MetricResult, Status, ok, withheld
from .common import check_nav, check_price, ttm_window
from .distributions import summarize_window

Series = Sequence[tuple]  # (date, Decimal level), any order


def premium_discount(price: Optional[PricePoint], nav: Optional[NavPoint], as_of: dt.date, *,
                     max_gap_days: int = 0, price_stale_days: int = 3, nav_stale_days: int = 3) -> MetricResult:
    name = "premium_discount_to_nav"
    px, pr, pf = check_price(price, as_of, price_stale_days)
    nv, nr, nf = check_nav(nav, as_of, nav_stale_days)
    if px is None or nv is None:
        return withheld(name, as_of, Status.UNAVAILABLE, pr + nr, "ratio", pf + nf)
    gap = abs((price.date - nav.nav_date).days)
    if gap > max_gap_days:
        return withheld(name, as_of, Status.UNAVAILABLE, [f"DATES_NOT_ALIGNED (gap {gap}d)"], "ratio", pf + nf)
    sid = {s for s in (price.source_id, nav.source_id) if s}
    return ok(name, as_of, px / nv - 1, "ratio", pf + nf, sid,
              [("price", str(px)), ("nav", str(nv)), ("date", price.date.isoformat())])


def _level_on_or_before(series: Series, target: dt.date, max_gap_days: int):
    cands = [(d, v) for d, v in series if d <= target]
    if not cands:
        return None
    d, v = max(cands, key=lambda x: x[0])
    return (d, v) if (target - d).days <= max_gap_days else None


def _span_return(series: Series, start: dt.date, end: dt.date, max_gap_days: int):
    a = _level_on_or_before(series, start, max_gap_days)
    b = _level_on_or_before(series, end, max_gap_days)
    if a is None or b is None:
        return None, ["SERIES_DOES_NOT_COVER_WINDOW"]
    if a[1] <= 0 or b[1] <= 0:
        return None, ["LEVEL_NOT_POSITIVE"]
    if b[0] <= a[0]:
        return None, ["WINDOW_HAS_NO_SPAN"]
    return (b[1] / a[1] - 1, (b[0] - a[0]).days), []


def _annualise(simple: Decimal, days: int) -> Decimal:
    return Decimal(float(1 + simple) ** (365.0 / days) - 1)


def nav_return(instrument: Instrument, navs: Sequence[NavPoint], start: dt.date, end: dt.date, as_of: dt.date,
               *, max_gap_days: int = 5, name: str = "nav_return") -> MetricResult:
    if end > as_of:
        return withheld(name, as_of, Status.UNAVAILABLE, ["WINDOW_END_AFTER_AS_OF"], "ratio")
    series = [(n.nav_date, n.nav) for n in navs if n.instrument_key == instrument.key]
    r, why = _span_return(series, start, end, max_gap_days)
    if r is None:
        return withheld(name, as_of, Status.UNAVAILABLE, why, "ratio")
    simple, days = r
    flags = [] if all(n.grade in VERIFIED_GRADES for n in navs if n.instrument_key == instrument.key) \
        else ["NAV_UNVERIFIED"]
    if instrument.distributes:
        flags.append("EXCLUDES_DISTRIBUTIONS")
    if days >= 365:
        return ok(name, as_of, simple, "ratio", flags, {n.source_id for n in navs if n.source_id},
                  [("span_days", str(days)), ("cagr", str(_annualise(simple, days)))])
    return ok(name, as_of, simple, "ratio", flags, {n.source_id for n in navs if n.source_id},
              [("span_days", str(days))])


def nav_cagr(instrument: Instrument, navs: Sequence[NavPoint], start: dt.date, end: dt.date, as_of: dt.date,
             *, max_gap_days: int = 5) -> MetricResult:
    """Annualised NAV return; unavailable for spans shorter than 365 days (annualising short spans misleads)."""
    name = "nav_cagr"
    series = [(n.nav_date, n.nav) for n in navs if n.instrument_key == instrument.key]
    r, why = _span_return(series, start, end, max_gap_days)
    if r is None:
        return withheld(name, as_of, Status.UNAVAILABLE, why, "ratio")
    simple, days = r
    if days < 365:
        return withheld(name, as_of, Status.UNAVAILABLE, ["SPAN_UNDER_365_DAYS"], "ratio")
    flags = ["EXCLUDES_DISTRIBUTIONS"] if instrument.distributes else []
    return ok(name, as_of, _annualise(simple, days), "ratio", flags)


def tracking_difference(instrument: Instrument, navs: Sequence[NavPoint], benchmark: Series, start: dt.date,
                        end: dt.date, as_of: dt.date, *, max_gap_days: int = 5) -> MetricResult:
    name = "tracking_difference"
    series = [(n.nav_date, n.nav) for n in navs if n.instrument_key == instrument.key]
    f, why_f = _span_return(series, start, end, max_gap_days)
    b, why_b = _span_return(benchmark, start, end, max_gap_days)
    if f is None or b is None:
        return withheld(name, as_of, Status.UNAVAILABLE, [f"FUND_{w}" for w in why_f] + [f"BENCHMARK_{w}" for w in why_b], "ratio")
    if f[1] != b[1]:
        return withheld(name, as_of, Status.UNAVAILABLE, ["FUND_AND_BENCHMARK_SPANS_DIFFER"], "ratio")
    flags = ["BENCHMARK_LICENCE_NOT_CLEARED"]
    if instrument.distributes:
        flags.append("EXCLUDES_DISTRIBUTIONS")
    return ok(name, as_of, f[0] - b[0], "ratio", flags, {n.source_id for n in navs if n.source_id},
              [("fund_return", str(f[0])), ("benchmark_return", str(b[0]))])


def trailing_distribution_yield(instrument: Instrument, events: Sequence[DistributionEvent],
                                price: Optional[PricePoint], as_of: dt.date) -> MetricResult:
    name = "trailing_distribution_yield"
    if instrument.distributes is False:
        return withheld(name, as_of, Status.NOT_APPLICABLE, ["SCHEME_DOES_NOT_DISTRIBUTE"], "ratio")
    if instrument.distributes is None:
        return withheld(name, as_of, Status.UNAVAILABLE, ["DISTRIBUTION_POLICY_UNKNOWN"], "ratio")
    px, pr, pf = check_price(price, as_of)
    t0, t1 = ttm_window(as_of)
    w = summarize_window([e for e in events if e.instrument_key == instrument.key], t0, t1)
    if px is None or w.n == 0:
        return withheld(name, as_of, Status.UNAVAILABLE, pr + (["NO_TTM_DISTRIBUTIONS"] if w.n == 0 else []), "ratio", pf)
    flags = pf + ["NO_COMPONENT_SPLIT"]
    if w.n_unverified_amount:
        flags.append("UNVERIFIED_SOURCE")
    if w.n_unavailable:
        flags.append("AMOUNT_UNAVAILABLE_IN_WINDOW")
    return ok(name, as_of, w.total / px, "ratio", flags, w.source_ids, [("ttm_total", str(w.total)), ("price", str(px))])


HOLDINGS_STALE_DAYS = 45      # assumption: monthly portfolio disclosure plus publication lag; configurable


def holdings_top10_weight(instrument: Instrument, holdings: Sequence, as_of: dt.date, *,
                          stale_days: int = HOLDINGS_STALE_DAYS) -> MetricResult:
    """Sum of the ten largest holding weights in the latest disclosed portfolio (top-N if fewer than ten names).
    The portfolio must sum to 98-100.5%: a partial list would make the figure meaningless, so it is refused. Needs the
    holdings as-of date; older than stale_days is flagged HOLDINGS_STALE (blocking)."""
    name = "holdings_top10_weight"
    mine = [h for h in holdings if h.etf_key == instrument.key and h.as_of <= as_of]
    if not mine:
        return withheld(name, as_of, Status.UNAVAILABLE, ["HOLDINGS_NOT_SUPPLIED"], "ratio")
    latest = max(h.as_of for h in mine)
    cur = [h for h in mine if h.as_of == latest]
    total = sum((h.weight for h in cur), Decimal(0))
    if not (Decimal("0.98") <= total <= Decimal("1.005")):
        return withheld(name, as_of, Status.UNAVAILABLE, [f"HOLDINGS_INCOMPLETE (weights sum to {total:.4f})"], "ratio")
    top = sorted((h.weight for h in cur), reverse=True)[:10]
    flags = ["HOLDINGS_STALE"] if (as_of - latest).days > stale_days else []
    if len(cur) < 10:
        flags.append("FEWER_THAN_10_HOLDINGS")
    return ok(name, as_of, sum(top, Decimal(0)), "ratio", flags, {h.source_id for h in cur if h.source_id},
              [("as_of_holdings", latest.isoformat()), ("names", str(len(cur)))])
