"""Domain model. Amounts are Decimal; a missing value is None, never zero."""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Optional


class InstrumentType(str, enum.Enum):
    REIT = "REIT"
    INVIT = "INVIT"
    ETF = "ETF"


class ETFCategory(str, enum.Enum):
    EQUITY_BROAD = "EQUITY_BROAD"
    EQUITY_SECTOR_THEMATIC_FACTOR = "EQUITY_SECTOR_THEMATIC_FACTOR"
    GOLD_SILVER = "GOLD_SILVER"
    DEBT = "DEBT"
    INTERNATIONAL = "INTERNATIONAL"
    OTHER = "OTHER"


class SourceGrade(str, enum.Enum):
    EXCHANGE = "EXCHANGE"
    ISSUER = "ISSUER"
    REGULATOR = "REGULATOR"
    AGGREGATOR = "AGGREGATOR"
    UNKNOWN = "UNKNOWN"


VERIFIED_GRADES = frozenset({SourceGrade.EXCHANGE, SourceGrade.ISSUER, SourceGrade.REGULATOR})


class ComponentType(str, enum.Enum):
    INTEREST = "INTEREST"
    DIVIDEND = "DIVIDEND"
    RENTAL = "RENTAL"                      # REIT only
    OTHER_INCOME = "OTHER_INCOME"          # other / treasury income, not assumed recurring
    CAPITAL_REPAYMENT = "CAPITAL_REPAYMENT"  # return of capital, SPV debt/loan repayment, capital reduction


class ComponentClass(str, enum.Enum):
    INCOME = "INCOME"
    OTHER = "OTHER"
    CAPITAL = "CAPITAL"


COMPONENT_CLASS: Mapping[ComponentType, ComponentClass] = {
    ComponentType.INTEREST: ComponentClass.INCOME,
    ComponentType.DIVIDEND: ComponentClass.INCOME,
    ComponentType.RENTAL: ComponentClass.INCOME,
    ComponentType.OTHER_INCOME: ComponentClass.OTHER,
    ComponentType.CAPITAL_REPAYMENT: ComponentClass.CAPITAL,
}

# Component types a disclosure may legitimately carry, by instrument type.
# ETFs have no component split in this model: a split is never invented for them.
ALLOWED_COMPONENTS: Mapping[InstrumentType, frozenset] = {
    InstrumentType.INVIT: frozenset({ComponentType.INTEREST, ComponentType.DIVIDEND,
                                     ComponentType.OTHER_INCOME, ComponentType.CAPITAL_REPAYMENT}),
    InstrumentType.REIT: frozenset(ComponentType),
    InstrumentType.ETF: frozenset(),
}


class NavKind(str, enum.Enum):
    FAIR_VALUE = "FAIR_VALUE"   # Reg 10 style fair-value NAV (REIT/InvIT)
    BOOK = "BOOK"
    FUND_NAV = "FUND_NAV"       # ETF scheme NAV


class LeverageDefinition(str, enum.Enum):
    """Definitions differ by issuer and are NOT comparable; the definition always travels with the value."""
    SEBI_NET_BORROWINGS_RATIO = "SEBI_NET_BORROWINGS_RATIO"
    NET_DEBT_TO_GAV = "NET_DEBT_TO_GAV"
    NET_DEBT_TO_EV = "NET_DEBT_TO_EV"
    DEBT_TO_EV = "DEBT_TO_EV"
    NET_DEBT_TO_AUM = "NET_DEBT_TO_AUM"
    OTHER = "OTHER"


@dataclass(frozen=True)
class Instrument:
    key: str
    name: str
    type: InstrumentType
    etf_category: Optional[ETFCategory] = None
    distributes: Optional[bool] = None  # ETF payout policy; None = unknown
    isin: Optional[str] = None
    symbols: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Source:
    source_id: str
    name: str
    grade: SourceGrade
    url: str = ""
    # Licensing gate. Default False for everything: no source is cleared for public display.
    display_cleared: bool = False
    comment: str = ""


@dataclass(frozen=True)
class DistributionEvent:
    event_id: str
    instrument_key: str
    ex_date: dt.date
    record_date: Optional[dt.date]
    total_per_unit: Optional[Decimal]          # None = amount unavailable
    components: Mapping[ComponentType, Decimal] = field(default_factory=dict)  # only what the source disclosed
    include: bool = True                       # False removes the row from every calculation
    amount_grade: SourceGrade = SourceGrade.UNKNOWN
    source_id: str = ""
    period_label: str = ""
    status_text: str = ""
    notes: str = ""


@dataclass(frozen=True)
class PricePoint:
    instrument_key: str
    date: dt.date
    price: Decimal
    venue: str = ""
    source_id: str = ""


@dataclass(frozen=True)
class NavPoint:
    instrument_key: str
    nav_date: dt.date
    nav: Decimal
    kind: NavKind = NavKind.FAIR_VALUE
    grade: SourceGrade = SourceGrade.UNKNOWN
    source_id: str = ""


@dataclass(frozen=True)
class LeveragePoint:
    instrument_key: str
    date: dt.date
    value: Decimal
    definition: LeverageDefinition
    grade: SourceGrade = SourceGrade.UNKNOWN
    source_id: str = ""
    definition_note: str = ""


@dataclass(frozen=True)
class Holding:
    etf_key: str
    as_of: dt.date
    isin: str
    name: str
    weight: Decimal
    source_id: str = ""
