"""Cross-source verification. Two sources reporting the same observation must agree; if they do not, BOTH are kept,
the disagreement is recorded, affected metrics get the blocking flag SOURCE_DISCREPANCY, and the engine only
proceeds with a value when one source clearly outranks the other. Ties are never broken arbitrarily.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .models import DistributionEvent, SourceGrade
from .result import MetricResult

GRADE_RANK = {SourceGrade.EXCHANGE: 5, SourceGrade.ISSUER: 4, SourceGrade.REGULATOR: 3,
              SourceGrade.AGGREGATOR: 2, SourceGrade.UNKNOWN: 1}
TOLERANCE = {"price": Decimal("0.005"), "nav": Decimal("0.005"), "distribution": Decimal("0.0051"),
             "leverage": Decimal("0.0005")}

AFFECTED = {
    "price": ("ttm_yield", "income_yield", "other_yield", "capital_repayment_yield", "premium_to_nav",
              "premium_discount_to_nav", "trailing_distribution_yield"),
    "nav": ("premium_to_nav", "premium_discount_to_nav", "nav_return_1y", "tracking_difference_1y"),
    "distribution": ("ttm_dpu", "payments_ttm", "ttm_yield", "income_yield", "other_yield", "capital_repayment_yield",
                     "income_share", "other_share", "capital_repayment_share", "yoy_total_dpu", "yoy_income_dpu",
                     "payment_size_cv", "largest_payment_share", "trailing_distribution_yield"),
    "leverage": ("reported_leverage", "net_debt_to_gav"),
}


@dataclass(frozen=True)
class Obs:
    source_id: str
    grade: SourceGrade
    date: dt.date
    value: Decimal
    retrieved_at: str = ""


@dataclass(frozen=True)
class Discrepancy:
    instrument_key: str
    field: str
    ref_date: dt.date
    source_a: str
    value_a: Decimal
    source_b: str
    value_b: Decimal

    @property
    def abs_diff(self) -> Decimal:
        return abs(self.value_a - self.value_b)


def resolve(instrument_key: str, field: str, group: Sequence[Obs]) -> Tuple[Optional[Obs], List[Discrepancy]]:
    """Pick the value to use for one observation identity (same instrument/date/venue) seen by several sources.
    Returns (chosen or None, discrepancies). One source -> it. Sources agreeing within tolerance -> highest grade
    (corroborated). Disagreeing -> the unique highest-grade source, else None (unresolved)."""
    by_src: Dict[str, Obs] = {}
    for o in group:       # latest retrieval wins within one source
        if o.source_id not in by_src or o.retrieved_at > by_src[o.source_id].retrieved_at:
            by_src[o.source_id] = o
    obs = sorted(by_src.values(), key=lambda o: (-GRADE_RANK[o.grade], o.source_id))
    if len(obs) == 1:
        return obs[0], []
    tol = TOLERANCE[field]
    top = obs[0]
    disc = [Discrepancy(instrument_key, field, top.date, top.source_id, top.value, o.source_id, o.value)
            for o in obs[1:] if abs(o.value - top.value) > tol]
    if not disc:
        return top, []
    tied = [o for o in obs if GRADE_RANK[o.grade] == GRADE_RANK[top.grade] and abs(o.value - top.value) > tol]
    return (None if tied else top), disc


def reconcile_events(events: Sequence[DistributionEvent]) -> Tuple[List[DistributionEvent], List[Discrepancy]]:
    """Make multi-source distribution events safe to sum. Same payment from two sources must not be double-counted:
    corroborated duplicates are excluded (include=False) in favour of the highest-grade source; disagreeing sources
    keep the unique top-grade source, and a tie turns the date into an amount-unavailable placeholder, which the engine
    flags AMOUNT_UNAVAILABLE_IN_WINDOW. Multiple records from ONE source on a date stay additive (reviewed at import)."""
    groups: Dict[tuple, List[DistributionEvent]] = {}
    for e in events:
        groups.setdefault((e.instrument_key, e.ex_date), []).append(e)
    out: List[DistributionEvent] = []
    discs: List[Discrepancy] = []
    tol = TOLERANCE["distribution"]
    for (key, ex), evs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        priced = [e for e in evs if e.include and e.total_per_unit is not None]
        sources = {e.source_id for e in priced}
        if len(sources) < 2:
            out.extend(evs)
            continue
        sub: Dict[str, Decimal] = {s: sum((e.total_per_unit for e in priced if e.source_id == s), Decimal(0)) for s in sources}
        grade = {s: max((e.amount_grade for e in priced if e.source_id == s), key=lambda g: GRADE_RANK[g]) for s in sources}
        ranked = sorted(sources, key=lambda s: (-GRADE_RANK[grade[s]], s))
        top = ranked[0]
        bad = [s for s in ranked[1:] if abs(sub[s] - sub[top]) > tol]
        for s in bad:
            discs.append(Discrepancy(key, "distribution", ex, top, sub[top], s, sub[s]))
        tied = [s for s in bad if GRADE_RANK[grade[s]] == GRADE_RANK[grade[top]]]
        if tied:
            mark = dataclasses.replace(priced[0], total_per_unit=None, components={}, include=False,
                                       status_text="DISCREPANCY_UNRESOLVED", amount_grade=SourceGrade.UNKNOWN)
            out.append(mark)
            out.extend(dataclasses.replace(e, include=False, status_text="EXCLUDED_DISCREPANCY") for e in evs
                       if e not in priced)
            continue
        for e in evs:
            if e in priced and e.source_id != top:
                out.append(dataclasses.replace(
                    e, include=False,
                    status_text="EXCLUDED_DISCREPANCY" if e.source_id in bad else "EXCLUDED_DUPLICATE_OF_" + top))
            else:
                out.append(e)
    return out, discs


def apply_flags(results: Mapping[str, MetricResult], discrepancies: Iterable[Discrepancy]) -> Dict[str, MetricResult]:
    out = dict(results)
    for d in discrepancies:
        for name in AFFECTED[d.field]:
            if name in out:
                out[name] = out[name].with_flags("SOURCE_DISCREPANCY")
    return out
