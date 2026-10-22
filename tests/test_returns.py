import datetime as dt
from decimal import Decimal as D

import pytest

from irie.calc.returns import Lot, portfolio_ledger, xirr
from irie.models import ComponentType as C
from tests.helpers import AS_OF, ev, px

d = dt.date.fromisoformat


def test_xirr_known_values():
    assert abs(xirr([(d("2025-01-01"), D(-100)), (d("2026-01-01"), D(110))]) - 0.10) < 1e-9
    assert abs(xirr([(d("2025-01-01"), D(-100)), (d("2026-01-01"), D(0)), (d("2027-01-01"), D(121))]) - 0.10) < 1e-9


def test_xirr_unavailable_without_both_signs_or_empty():
    assert xirr([]) is None
    assert xirr([(d("2025-01-01"), D(-100))]) is None
    assert xirr([(d("2025-01-01"), D(100)), (d("2026-01-01"), D(50))]) is None


def test_ledger_entitlement_is_strictly_before_ex_date_and_through_as_of():
    events = [ev("2026-03-01", 2, {C.INTEREST: "1.5", C.CAPITAL_REPAYMENT: "0.5"}), ev("2026-06-01", 3),
              ev("2026-11-01", 9)]                                                   # after as_of: never received
    lots = [Lot("T", d("2026-03-01"), D(10), D(100)),     # bought ON the ex-date: not entitled
            Lot("T", d("2026-02-28"), D(10), D(100))]     # day before: entitled
    led = portfolio_ledger(lots, events, {"T": px(110)}, AS_OF)
    assert led.distributions == D(80)    # lot A: 3 x 10 = 30 (June only); lot B: (2 + 3) x 10 = 50
    assert led.capital_repayment_received == D(10) * D("0.5")
    assert led.total_cost == D(2000) and led.market_value == D(2200)


def test_ledger_excludes_future_lots_and_reports_unpriced_instead_of_zero_valuing():
    lots = [Lot("T", d("2026-12-01"), D(10), D(100)), Lot("T", d("2026-01-01"), D(10), D(100))]
    led = portfolio_ledger(lots, [], {}, AS_OF)
    assert led.total_cost == D(1000) and led.lots_without_price == ["T"] and led.market_value == D(0)
    led2 = portfolio_ledger(lots, [], {"T": px(100, "2026-10-22")}, AS_OF)          # price dated after as_of is not used
    assert led2.lots_without_price == ["T"]
