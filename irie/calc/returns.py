"""Cash-flow return utilities: XIRR and a lot-level distribution ledger.

Pure arithmetic over lots the caller supplies (nothing is stored, nothing is recommended). Entitlement rule from
the workbook: a lot receives a distribution when purchase_date < ex_date <= as_of. Capital repayments are cash
and are counted once; they are reported separately because they lower the cost basis (no tax effect is modelled).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from ..models import COMPONENT_CLASS, ComponentClass, DistributionEvent, PricePoint

ZERO = Decimal(0)


@dataclass(frozen=True)
class Lot:
    instrument_key: str
    purchase_date: dt.date
    units: Decimal
    price_paid: Decimal
    charges: Decimal = ZERO


def xirr(flows: Sequence[tuple], tol: float = 1e-12) -> Optional[float]:
    """Annualised internal rate of return on dated flows, 365-day convention measured from the earliest
    date (Excel XIRR convention). Returns None unless there is at least one inflow and one outflow or if no
    root lies in (-99.99%, +1e6%). Bisection: slower than Newton but cannot diverge."""
    fl = [(d, float(v)) for d, v in flows if v != 0]
    if not fl or not any(v < 0 for _, v in fl) or not any(v > 0 for _, v in fl):
        return None
    d0 = min(d for d, _ in fl)

    def npv(r: float) -> float:
        return sum(v / (1.0 + r) ** ((d - d0).days / 365.0) for d, v in fl)

    lo, hi = -0.9999, 1e4
    flo, fhi = npv(lo), npv(hi)
    if flo * fhi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
        if hi - lo < tol:
            break
    return (lo + hi) / 2


@dataclass
class PortfolioLedger:
    flows: list
    total_cost: Decimal
    market_value: Decimal
    distributions: Decimal
    capital_repayment_received: Decimal
    lots_without_price: list


def portfolio_ledger(lots: Sequence[Lot], events: Sequence[DistributionEvent],
                     prices: Mapping[str, PricePoint], as_of: dt.date) -> PortfolioLedger:
    flows, cost, mv, dist, cap, unpriced = [], ZERO, ZERO, ZERO, ZERO, []
    for lot in lots:
        if lot.purchase_date > as_of or lot.units <= 0:
            continue                     # future-dated or empty lots are excluded, never silently dated today
        c = lot.units * lot.price_paid + lot.charges
        cost += c
        flows.append((lot.purchase_date, -c))
        px = prices.get(lot.instrument_key)
        if px is None or px.date > as_of:
            unpriced.append(lot.instrument_key)
        else:
            mv += lot.units * px.price
        for ev in events:
            if (ev.instrument_key == lot.instrument_key and ev.include and ev.total_per_unit is not None
                    and lot.purchase_date < ev.ex_date <= as_of):
                amt = lot.units * ev.total_per_unit
                dist += amt
                flows.append((ev.ex_date, amt))
                cap += lot.units * sum((v for t, v in ev.components.items()
                                        if COMPONENT_CLASS[t] is ComponentClass.CAPITAL), ZERO)
    if mv:
        flows.append((as_of, mv))
    return PortfolioLedger(flows, cost, mv, dist, cap, unpriced)
