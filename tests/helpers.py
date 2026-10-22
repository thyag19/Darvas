import datetime as dt
from decimal import Decimal

from irie.models import (ComponentType as C, DistributionEvent, ETFCategory, Instrument, InstrumentType, NavKind,
                         NavPoint, PricePoint, SourceGrade)

D = Decimal
INVIT = Instrument("T", "Test InvIT", InstrumentType.INVIT)
REIT = Instrument("R", "Test REIT", InstrumentType.REIT)
AS_OF = dt.date(2026, 10, 21)


def ev(ex, total, comps=None, include=True, grade=SourceGrade.EXCHANGE, key="T", sid="S14", n=[0]):
    n[0] += 1
    return DistributionEvent(f"{key}:{ex}:{n[0]}", key, dt.date.fromisoformat(ex), None,
                             None if total is None else D(str(total)),
                             {k: D(str(v)) for k, v in (comps or {}).items()}, include, grade, sid)


def px(price, date="2026-10-21", key="T"):
    return PricePoint(key, dt.date.fromisoformat(date), D(str(price)), "NSE")


def nav(value, date, key="T", grade=SourceGrade.ISSUER, kind=NavKind.FAIR_VALUE):
    return NavPoint(key, dt.date.fromisoformat(date), D(str(value)), kind, grade)
