"""Metric registry: which metric is defined for which instrument type/category, and what it needs.

The registry is what stops one formula being forced onto every instrument. A request for a metric that is not
defined for an instrument returns NOT_APPLICABLE with the reason; a defined metric whose inputs are missing
returns UNAVAILABLE. Neither is ever zero.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Dict, Optional, Sequence, Tuple

from .calc import distributions as dist
from .calc import etf as etfcalc
from .calc import valuation
from .models import (DistributionEvent, ETFCategory, Instrument, InstrumentType, LeveragePoint, NavPoint,
                     PricePoint)
from .result import MetricResult, Status, withheld


@dataclass
class Snapshot:
    """Everything needed to compute metrics for one instrument at one explicit report date."""
    instrument: Instrument
    as_of: dt.date                                   # required: no implicit "today" anywhere in the engine
    events: Sequence[DistributionEvent] = ()
    price: Optional[PricePoint] = None
    nav: Optional[NavPoint] = None                   # latest periodic NAV (REIT/InvIT) or latest fund NAV (ETF)
    navs: Sequence[NavPoint] = ()                    # ETF NAV history
    leverage: Optional[LeveragePoint] = None
    net_debt: Optional[Decimal] = None               # REIT inputs for net_debt_to_gav
    gav: Optional[Decimal] = None
    benchmark: Sequence[tuple] = ()                  # ETF benchmark levels [(date, level)], licence not cleared
    manual_partial_history: bool = False


@dataclass(frozen=True)
class MetricSpec:
    name: str
    types: frozenset
    etf_categories: Optional[frozenset]  # None = all categories of an applicable ETF
    requires: Tuple[str, ...]
    definition: str


_RI = frozenset({InstrumentType.REIT, InstrumentType.INVIT})
_ETF = frozenset({InstrumentType.ETF})
_EQ_LIKE = frozenset({ETFCategory.EQUITY_BROAD, ETFCategory.EQUITY_SECTOR_THEMATIC_FACTOR,
                      ETFCategory.INTERNATIONAL, ETFCategory.GOLD_SILVER})

SPECS: Dict[str, MetricSpec] = {s.name: s for s in [
    MetricSpec("ttm_dpu", _RI, None, ("events", "as_of"), "Sum of included per-unit distributions with ex-date in (as_of-365d, as_of]"),
    MetricSpec("payments_ttm", _RI, None, ("events",), "Count of included payments in the TTM window"),
    MetricSpec("ttm_yield", _RI, None, ("events", "price"), "TTM DPU / price. Headline: includes capital repayment; read with the split."),
    MetricSpec("income_yield", _RI, None, ("events", "price"), "(interest + dividend [+ rental for REIT]) per unit / price; needs COMPLETE verified components"),
    MetricSpec("other_yield", _RI, None, ("events", "price"), "Other/treasury income per unit / price; not assumed recurring"),
    MetricSpec("capital_repayment_yield", _RI, None, ("events", "price"), "Capital repayment per unit / price; needs COMPLETE verified components"),
    MetricSpec("income_share", _RI, None, ("events",), "Income components / TTM total"),
    MetricSpec("other_share", _RI, None, ("events",), "Other components / TTM total"),
    MetricSpec("capital_repayment_share", _RI, None, ("events",), "Capital repayment / TTM total (single definition)"),
    MetricSpec("yoy_total_dpu", _RI, None, ("events",), "TTM total / prior-12M total - 1, gated on history check; includes capital repayment"),
    MetricSpec("yoy_income_dpu", _RI, None, ("events",), "TTM income / prior-12M income - 1; needs COMPLETE components in both windows"),
    MetricSpec("payment_size_cv", _RI, None, ("events",), "Sample std dev / mean of TTM payment sizes (descriptive only)"),
    MetricSpec("largest_payment_share", _RI, None, ("events",), "Largest TTM payment / TTM total"),
    MetricSpec("premium_to_nav", _RI, None, ("price", "nav"), "price / fair-value NAV - 1, NAV date shown"),
    MetricSpec("reported_leverage", _RI, None, ("leverage",), "Disclosed leverage with its definition; not comparable across issuers"),
    MetricSpec("net_debt_to_gav", frozenset({InstrumentType.REIT}), None, ("net_debt", "gav"), "REIT net debt / gross asset value"),
    MetricSpec("premium_discount_to_nav", _ETF, None, ("price", "nav"), "price / NAV - 1 on the same date"),
    MetricSpec("nav_return_1y", _ETF, None, ("navs",), "NAV(as_of)/NAV(as_of-365d)-1; excludes distributions"),
    MetricSpec("trailing_distribution_yield", _ETF, None, ("events", "price"), "TTM distributions / price; only for schemes known to distribute; no component split"),
    MetricSpec("tracking_difference_1y", _ETF, _EQ_LIKE, ("navs", "benchmark"), "1y fund NAV return - benchmark return; not tracking error"),
]}


def applicability(inst: Instrument, spec: MetricSpec) -> Optional[str]:
    """None if the metric is defined for this instrument, else the reason it is not."""
    if inst.type not in spec.types:
        return f"{spec.name} is not defined for {inst.type.value}"
    if inst.type is InstrumentType.ETF and spec.etf_categories is not None:
        if inst.etf_category is None:
            return f"{spec.name} needs an ETF category; none set"
        if inst.etf_category not in spec.etf_categories:
            return f"{spec.name} is not defined for ETF category {inst.etf_category.value}"
    return None


def compute_all(snap: Snapshot, price_stale_days: int = 3) -> Dict[str, MetricResult]:
    inst, as_of = snap.instrument, snap.as_of
    out: Dict[str, MetricResult] = {}
    analysis = None
    if inst.type in (InstrumentType.REIT, InstrumentType.INVIT):
        analysis = dist.analyze_distributions(inst, snap.events, snap.price, as_of, price_stale_days=price_stale_days,
                                              manual_partial=snap.manual_partial_history)
    year = dt.timedelta(days=365)
    for name, spec in SPECS.items():
        why = applicability(inst, spec)
        if why:
            out[name] = withheld(name, as_of, Status.NOT_APPLICABLE, [why])
            continue
        if analysis is not None and name in analysis.metrics:
            out[name] = analysis.metrics[name]
        elif name == "premium_to_nav":
            out[name] = valuation.premium_to_nav(snap.price, snap.nav, as_of, price_stale_days=price_stale_days)
        elif name == "reported_leverage":
            out[name] = valuation.reported_leverage(snap.leverage, as_of)
        elif name == "net_debt_to_gav":
            out[name] = valuation.net_debt_to_gav(snap.net_debt, snap.gav, as_of)
        elif name == "premium_discount_to_nav":
            out[name] = etfcalc.premium_discount(snap.price, snap.nav, as_of)
        elif name == "nav_return_1y":
            out[name] = etfcalc.nav_return(inst, snap.navs, as_of - year, as_of, as_of, name=name)
        elif name == "trailing_distribution_yield":
            out[name] = etfcalc.trailing_distribution_yield(inst, snap.events, snap.price, as_of)
        elif name == "tracking_difference_1y":
            res = etfcalc.tracking_difference(inst, snap.navs, snap.benchmark, as_of - year, as_of, as_of)
            out[name] = res
        else:  # pragma: no cover - guards against a spec without an implementation
            raise NotImplementedError(name)
    return out
