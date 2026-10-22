"""Distribution analysis shared by REITs and InvITs.

Definitions are those of the audited workbook (ex-date TTM window, source-verified components that must
reconcile to the total), with the Phase 1 defects fixed:
  * headline yield is always accompanied by the income / other / capital-repayment split, or an explicit
    reason why the split is unavailable (C2);
  * unavailable data is never shown as zero (C5);
  * one definition of capital share (C6);
  * unverified-source amounts raise a blocking flag instead of silently scoring (C1);
  * growth is available for income as well as total, because total includes capital repayment (C7).
No ranking, no tax, no forecast.
"""
from __future__ import annotations

import datetime as dt
import enum
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from ..models import (ALLOWED_COMPONENTS, COMPONENT_CLASS, VERIFIED_GRADES, ComponentClass, ComponentType,
                      DistributionEvent, Instrument, InstrumentType, PricePoint)
from ..result import MetricResult, Status, ok, withheld
from .common import check_price, prior_window, ttm_window

TOLERANCE = Decimal("0.0051")  # per-record rounding tolerance (2-dp disclosures), from the workbook
ZERO = Decimal(0)


class ComponentStatus(str, enum.Enum):
    NOT_DISCLOSED = "NOT_DISCLOSED"
    RECONCILES = "RECONCILES"
    DOES_NOT_RECONCILE = "DOES_NOT_RECONCILE"


class Coverage(str, enum.Enum):
    COMPLETE = "COMPLETE"          # every payment in the window has verified, reconciling components
    PARTIAL = "PARTIAL"
    NONE = "NONE"                  # payments exist, no verified components
    NO_PAYMENTS = "NO_PAYMENTS"


class HistoryCheck(str, enum.Enum):
    OK = "OK"
    UNAVAILABLE_AMOUNTS = "INCOMPLETE_UNAVAILABLE_AMOUNTS"
    SHORT_HISTORY = "INCOMPLETE_SHORT_HISTORY"
    NO_AMOUNTS = "NO_AMOUNTS"
    NO_DATA = "NO_DATA"
    MANUAL_PARTIAL = "PARTIAL_MANUAL"


def component_status(ev: DistributionEvent, tolerance: Decimal = TOLERANCE) -> ComponentStatus:
    if not ev.components:
        return ComponentStatus.NOT_DISCLOSED
    if ev.total_per_unit is None:
        return ComponentStatus.DOES_NOT_RECONCILE
    diff = abs(sum(ev.components.values(), ZERO) - ev.total_per_unit)
    return ComponentStatus.RECONCILES if diff <= tolerance else ComponentStatus.DOES_NOT_RECONCILE


def components_verified(ev: DistributionEvent, tolerance: Decimal = TOLERANCE) -> bool:
    return component_status(ev, tolerance) is ComponentStatus.RECONCILES and ev.amount_grade in VERIFIED_GRADES


def has_amount(ev: DistributionEvent) -> bool:
    return ev.total_per_unit is not None


@dataclass
class WindowSummary:
    start_excl: dt.date
    end_incl: dt.date
    n: int = 0
    total: Decimal = ZERO
    amounts: list = field(default_factory=list)
    n_unavailable: int = 0            # in-window events with no amount (excluded, never zero)
    n_unverified_amount: int = 0      # in-window amounts whose source is not exchange/issuer/regulator
    n_components_verified: int = 0
    n_components_mismatch: int = 0
    sums: dict = field(default_factory=lambda: {c: ZERO for c in ComponentType})
    source_ids: set = field(default_factory=set)
    coverage: Coverage = Coverage.NO_PAYMENTS

    def class_sum(self, cls: ComponentClass) -> Decimal:
        return sum((v for t, v in self.sums.items() if COMPONENT_CLASS[t] is cls), ZERO)

    @property
    def largest(self) -> Optional[Decimal]:
        return max(self.amounts) if self.amounts else None


def summarize_window(events: Iterable[DistributionEvent], start_excl: dt.date, end_incl: dt.date,
                     tolerance: Decimal = TOLERANCE) -> WindowSummary:
    w = WindowSummary(start_excl, end_incl)
    for ev in events:
        if not (start_excl < ev.ex_date <= end_incl):
            continue
        if not ev.include and has_amount(ev):
            continue                     # deliberately excluded (e.g. confirmed duplicate)
        if not has_amount(ev) or not ev.include:
            w.n_unavailable += 1
            continue
        w.n += 1
        w.total += ev.total_per_unit
        w.amounts.append(ev.total_per_unit)
        w.source_ids.add(ev.source_id)
        if ev.amount_grade not in VERIFIED_GRADES:
            w.n_unverified_amount += 1
        st = component_status(ev, tolerance)
        if st is ComponentStatus.DOES_NOT_RECONCILE:
            w.n_components_mismatch += 1
        if components_verified(ev, tolerance):
            w.n_components_verified += 1
            for t, v in ev.components.items():
                w.sums[t] += v
    if w.n == 0:
        w.coverage = Coverage.NO_PAYMENTS
    elif w.n_components_verified == w.n:
        w.coverage = Coverage.COMPLETE
    elif w.n_components_verified == 0:
        w.coverage = Coverage.NONE
    else:
        w.coverage = Coverage.PARTIAL
    return w


def history_check(events: Sequence[DistributionEvent], as_of: dt.date,
                  manual_partial: bool = False) -> HistoryCheck:
    """Whether a year-on-year comparison is trustworthy (workbook DISTRIBUTION HISTORY!M)."""
    cutoff = as_of - dt.timedelta(days=730)
    included = [e for e in events if e.include and has_amount(e)]
    unavailable = [e for e in events if (not has_amount(e)) and cutoff < e.ex_date <= as_of]
    if not included:
        return HistoryCheck.NO_AMOUNTS if unavailable else HistoryCheck.NO_DATA
    if unavailable:
        return HistoryCheck.UNAVAILABLE_AMOUNTS
    if min(e.ex_date for e in included) > cutoff:
        return HistoryCheck.SHORT_HISTORY
    return HistoryCheck.MANUAL_PARTIAL if manual_partial else HistoryCheck.OK


@dataclass
class DistributionAnalysis:
    metrics: dict
    ttm: WindowSummary
    prior: WindowSummary
    history: HistoryCheck


def _window_flags(w: WindowSummary) -> list:
    flags = []
    if w.n_unverified_amount:
        flags.append("UNVERIFIED_SOURCE")
    if w.n_unavailable:
        flags.append("AMOUNT_UNAVAILABLE_IN_WINDOW")
    if w.n_components_mismatch:
        flags.append("COMPONENTS_DO_NOT_RECONCILE")
    return flags


def analyze_distributions(instrument: Instrument, events: Sequence[DistributionEvent],
                          price: Optional[PricePoint], as_of: dt.date, *,
                          tolerance: Decimal = TOLERANCE, price_stale_days: int = 3,
                          manual_partial: bool = False) -> DistributionAnalysis:
    if instrument.type not in (InstrumentType.REIT, InstrumentType.INVIT):
        raise ValueError("analyze_distributions is defined for REIT and InvIT only; ETFs use irie.calc.etf")
    ev = [e for e in events if e.instrument_key == instrument.key]
    bad = [e for e in ev if set(e.components) - ALLOWED_COMPONENTS[instrument.type]]
    if bad:
        raise ValueError(f"{instrument.key}: component types not allowed for {instrument.type.value}: "
                         f"{sorted({c.value for e in bad for c in e.components if c not in ALLOWED_COMPONENTS[instrument.type]})}")
    t0, t1 = ttm_window(as_of)
    p0, p1 = prior_window(as_of)
    ttm = summarize_window(ev, t0, t1, tolerance)
    prior = summarize_window(ev, p0, p1, tolerance)
    hist = history_check(ev, as_of, manual_partial)
    m: dict = {}
    k = lambda name: dict(name=name, as_of=as_of)

    # --- TTM distribution per unit (HISTORICAL) ---
    wflags = _window_flags(ttm)
    if ttm.n == 0:
        reason = "ALL_AMOUNTS_UNAVAILABLE_IN_WINDOW" if ttm.n_unavailable else "NO_TTM_DISTRIBUTIONS"
        m["ttm_dpu"] = withheld("ttm_dpu", as_of, Status.UNAVAILABLE, [reason], "INR/unit", wflags)
    else:
        m["ttm_dpu"] = ok("ttm_dpu", as_of, ttm.total, "INR/unit", wflags, ttm.source_ids,
                          [("payments", str(ttm.n))])
    m["payments_ttm"] = ok("payments_ttm", as_of, Decimal(ttm.n), "count", (), ttm.source_ids) if ttm.n else \
        withheld("payments_ttm", as_of, Status.UNAVAILABLE, ["NO_TTM_DISTRIBUTIONS"], "count")

    # --- price ---
    px, preasons, pflags = check_price(price, as_of, price_stale_days)
    ylds = ("ttm_yield", "income_yield", "other_yield", "capital_repayment_yield")
    shares = ("income_share", "other_share", "capital_repayment_share")
    if not m["ttm_dpu"].ok or px is None:
        why = list(m["ttm_dpu"].reasons) + preasons
        for n in ylds:
            m[n] = withheld(n, as_of, Status.UNAVAILABLE, why, "ratio", wflags + pflags, ttm.source_ids)
    else:
        sid = ttm.source_ids | ({price.source_id} if price and price.source_id else set())
        fl = wflags + pflags
        m["ttm_yield"] = ok("ttm_yield", as_of, ttm.total / px, "ratio", fl, sid,
                            [("ttm_dpu", str(ttm.total)), ("price", str(px))])
        if ttm.coverage is Coverage.COMPLETE:
            sums = {"income_yield": ttm.class_sum(ComponentClass.INCOME),
                    "other_yield": ttm.class_sum(ComponentClass.OTHER),
                    "capital_repayment_yield": ttm.class_sum(ComponentClass.CAPITAL)}
            for n, s in sums.items():
                m[n] = ok(n, as_of, s / px, "ratio", fl, sid, [("component_sum", str(s)), ("price", str(px))])
        else:
            st = Status.PARTIAL if ttm.coverage is Coverage.PARTIAL else Status.UNAVAILABLE
            why = [f"COMPONENTS_{ttm.coverage.value}"]
            for n in ylds[1:]:
                m[n] = withheld(n, as_of, st, why, "ratio", fl, sid)
    # shares of TTM distributions (single definition of capital share: complete, verified, reconciling only)
    if ttm.coverage is Coverage.COMPLETE and ttm.total > 0:
        for n, cls in zip(shares, (ComponentClass.INCOME, ComponentClass.OTHER, ComponentClass.CAPITAL)):
            m[n] = ok(n, as_of, ttm.class_sum(cls) / ttm.total, "ratio", wflags, ttm.source_ids)
    else:
        st = Status.PARTIAL if ttm.coverage is Coverage.PARTIAL else Status.UNAVAILABLE
        for n in shares:
            m[n] = withheld(n, as_of, st, [f"COMPONENTS_{ttm.coverage.value}"], "ratio", wflags, ttm.source_ids)

    # --- growth, gated on history ---
    gate_ok = hist in (HistoryCheck.OK,)
    if gate_ok and m["ttm_dpu"].ok and prior.total > 0:
        m["yoy_total_dpu"] = ok("yoy_total_dpu", as_of, ttm.total / prior.total - 1, "ratio",
                                wflags + ["INCLUDES_CAPITAL_REPAYMENT"], ttm.source_ids | prior.source_ids)
    else:
        why = [f"HISTORY_{hist.value}"] if not gate_ok else (["PRIOR_WINDOW_EMPTY"] if prior.total <= 0 else
                                                           list(m["ttm_dpu"].reasons))
        m["yoy_total_dpu"] = withheld("yoy_total_dpu", as_of, Status.UNAVAILABLE, why, "ratio")
    pi = prior.class_sum(ComponentClass.INCOME)
    if (gate_ok and ttm.coverage is Coverage.COMPLETE and prior.coverage is Coverage.COMPLETE and pi > 0):
        m["yoy_income_dpu"] = ok("yoy_income_dpu", as_of, ttm.class_sum(ComponentClass.INCOME) / pi - 1, "ratio",
                                 wflags, ttm.source_ids | prior.source_ids)
    else:
        m["yoy_income_dpu"] = withheld("yoy_income_dpu", as_of, Status.UNAVAILABLE,
                                       ["NEEDS_COMPLETE_COMPONENTS_BOTH_WINDOWS_AND_OK_HISTORY"], "ratio")

    # --- payment-size dispersion (descriptive only; distorted by irregular tranches) ---
    if ttm.n >= 2 and ttm.total > 0:
        mean = ttm.total / ttm.n
        cv = Decimal(statistics.stdev(ttm.amounts)) / mean
        m["payment_size_cv"] = ok("payment_size_cv", as_of, cv, "ratio", ["IRREGULAR_TRANCHES_DISTORT"],
                                  ttm.source_ids)
    else:
        m["payment_size_cv"] = withheld("payment_size_cv", as_of, Status.UNAVAILABLE, ["FEWER_THAN_2_PAYMENTS"], "ratio")
    if ttm.n and ttm.total > 0:
        m["largest_payment_share"] = ok("largest_payment_share", as_of, ttm.largest / ttm.total, "ratio",
                                        (), ttm.source_ids)
    else:
        m["largest_payment_share"] = withheld("largest_payment_share", as_of, Status.UNAVAILABLE,
                                              ["NO_TTM_DISTRIBUTIONS"], "ratio")
    return DistributionAnalysis(m, ttm, prior, hist)
