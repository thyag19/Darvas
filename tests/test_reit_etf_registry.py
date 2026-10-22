import datetime as dt
from decimal import Decimal as D

import pytest

from irie.calc import etf as E
from irie.calc import valuation as V
from irie.models import (ETFCategory as Cat, Instrument, InstrumentType as T, LeverageDefinition as LD,
                         LeveragePoint, NavKind, SourceGrade as G)
from irie.registry import SPECS, Snapshot, applicability, compute_all
from irie.result import Status
from tests.helpers import AS_OF, ev, nav, px

d = dt.date.fromisoformat


def etf(cat=Cat.EQUITY_BROAD, distributes=False):
    return Instrument("E", "Test ETF", T.ETF, cat, distributes)


def navs(*pairs, key="E", grade=G.ISSUER):
    return [nav(v, dte, key, grade, NavKind.FUND_NAV) for dte, v in pairs]


# ---- REIT / InvIT valuation ------------------------------------------------------------------------------
def test_premium_to_nav_and_staleness():
    r = V.premium_to_nav(px(110), nav(100, "2026-06-30"), AS_OF)
    assert r.value == D("0.1") and not r.flags
    old = V.premium_to_nav(px(110), nav(100, "2025-12-31"), AS_OF)          # 294 days > 270
    assert old.ok and "NAV_STALE" in old.flags
    assert "NAV_UNVERIFIED" in V.premium_to_nav(px(110), nav(100, "2026-06-30", grade=G.UNKNOWN), AS_OF).flags
    assert V.premium_to_nav(px(110), None, AS_OF).reasons == ("NAV_MISSING",)
    assert V.premium_to_nav(px(110), nav(100, "2026-10-22"), AS_OF).reasons[0].startswith("NAV_AFTER_AS_OF")


def test_net_debt_to_gav():
    assert V.net_debt_to_gav(D(40), D(100), AS_OF, "S", True).value == D("0.4")
    assert V.net_debt_to_gav(D(-10), D(100), AS_OF, "S", True).value == D("-0.1")   # net cash is legitimate
    assert V.net_debt_to_gav(D(40), D(0), AS_OF).reasons == ("GAV_NOT_POSITIVE",)
    assert V.net_debt_to_gav(None, D(100), AS_OF).reasons == ("INPUT_MISSING",)
    assert "LEVERAGE_UNVERIFIED" in V.net_debt_to_gav(D(40), D(100), AS_OF).flags


def test_reported_leverage_carries_its_definition():
    lp = LeveragePoint("T", d("2026-06-30"), D("0.58"), LD.SEBI_NET_BORROWINGS_RATIO, G.ISSUER)
    r = V.reported_leverage(lp, AS_OF)
    assert r.ok and "DEFINITION_SEBI_NET_BORROWINGS_RATIO" in r.flags
    assert V.reported_leverage(None, AS_OF).value is None


# ---- ETF -----------------------------------------------------------------------------------------------
def test_premium_discount_needs_same_date():
    assert E.premium_discount(px(99, "2026-10-21", "E"), nav(100, "2026-10-21", "E"), AS_OF).value == D("-0.01")
    r = E.premium_discount(px(99, "2026-10-21", "E"), nav(100, "2026-10-20", "E"), AS_OF)
    assert r.value is None and "DATES_NOT_ALIGNED" in r.reasons[0]
    assert E.premium_discount(px(99, "2026-10-21", "E"), nav(100, "2026-10-20", "E"), AS_OF, max_gap_days=1).ok


def test_nav_return_and_cagr():
    s = navs(("2025-10-21", 100), ("2026-10-21", 112))
    r = E.nav_return(etf(), s, d("2025-10-21"), d("2026-10-21"), AS_OF)
    assert r.value == D("0.12")
    two = navs(("2024-10-21", 100), ("2026-10-21", 121))
    cagr = E.nav_cagr(etf(), two, d("2024-10-21"), d("2026-10-21"), AS_OF)
    assert abs(cagr.value - D("0.1")) < D("1e-4")                    # 21% over ~2y = 10% a year (730d basis)
    short = navs(("2026-04-21", 100), ("2026-10-21", 105))
    assert E.nav_cagr(etf(), short, d("2026-04-21"), d("2026-10-21"), AS_OF).reasons == ("SPAN_UNDER_365_DAYS",)


def test_nav_return_gap_and_future_window():
    s = navs(("2025-01-01", 100), ("2026-10-21", 112))
    assert E.nav_return(etf(), s, d("2025-10-21"), d("2026-10-21"), AS_OF).reasons == ("SERIES_DOES_NOT_COVER_WINDOW",)
    assert E.nav_return(etf(), s, d("2025-10-21"), d("2026-10-22"), AS_OF).reasons == ("WINDOW_END_AFTER_AS_OF",)


def test_nav_return_of_distributing_scheme_is_not_a_total_return():
    s = navs(("2025-10-21", 100), ("2026-10-21", 105))
    assert "EXCLUDES_DISTRIBUTIONS" in E.nav_return(etf(distributes=True), s, d("2025-10-21"), d("2026-10-21"), AS_OF).flags


def test_tracking_difference():
    fund = navs(("2025-10-21", 100), ("2026-10-21", 110))
    bench = [(d("2025-10-21"), D(1000)), (d("2026-10-21"), D(1120))]
    r = E.tracking_difference(etf(), fund, bench, d("2025-10-21"), d("2026-10-21"), AS_OF)
    assert r.value == D("-0.02") and "BENCHMARK_LICENCE_NOT_CLEARED" in r.flags
    assert E.tracking_difference(etf(), fund, [], d("2025-10-21"), d("2026-10-21"), AS_OF).value is None


def test_etf_distribution_yield_applicability():
    e = [ev("2026-06-01", 2, key="E")]
    p = px(100, key="E")
    assert E.trailing_distribution_yield(etf(distributes=False), e, p, AS_OF).status is Status.NOT_APPLICABLE
    assert E.trailing_distribution_yield(etf(distributes=None), e, p, AS_OF).reasons == ("DISTRIBUTION_POLICY_UNKNOWN",)
    r = E.trailing_distribution_yield(etf(distributes=True), e, p, AS_OF)
    assert r.value == D("0.02") and "NO_COMPONENT_SPLIT" in r.flags
    assert E.trailing_distribution_yield(etf(distributes=True), [], p, AS_OF).value is None


# ---- registry ------------------------------------------------------------------------------------------
def test_registry_never_applies_a_metric_outside_its_definition():
    snap = Snapshot(Instrument("R", "r", T.REIT), AS_OF)
    out = compute_all(snap)
    assert out["nav_return_1y"].status is Status.NOT_APPLICABLE
    assert out["premium_discount_to_nav"].status is Status.NOT_APPLICABLE
    assert out["net_debt_to_gav"].status is Status.UNAVAILABLE         # applicable to REIT, inputs missing
    invit = compute_all(Snapshot(Instrument("T", "t", T.INVIT), AS_OF))
    assert invit["net_debt_to_gav"].status is Status.NOT_APPLICABLE     # InvITs report differently-defined leverage
    assert "not defined for INVIT" in invit["net_debt_to_gav"].reasons[0]


def test_etf_gets_no_income_capital_split_or_distribution_metrics_of_reit_invit():
    out = compute_all(Snapshot(etf(), AS_OF))
    for n in ("ttm_dpu", "income_yield", "capital_repayment_share", "yoy_total_dpu", "premium_to_nav"):
        assert out[n].status is Status.NOT_APPLICABLE, n


def test_tracking_difference_not_defined_for_debt_etf():
    spec = SPECS["tracking_difference_1y"]
    assert applicability(etf(Cat.DEBT), spec) is not None
    assert applicability(etf(Cat.EQUITY_BROAD), spec) is None
    assert applicability(etf(None), spec) is not None                   # a category is required


def test_registry_end_to_end_etf():
    s = navs(("2025-10-21", 100), ("2026-10-21", 110))
    snap = Snapshot(etf(), AS_OF, price=px(110, key="E"), nav=s[-1], navs=s,
                    benchmark=[(d("2025-10-21"), D(1000)), (d("2026-10-21"), D(1100))])
    out = compute_all(snap)
    assert out["premium_discount_to_nav"].value == D(0)
    assert out["nav_return_1y"].value == D("0.1") and out["tracking_difference_1y"].value == D(0)
    assert out["trailing_distribution_yield"].status is Status.NOT_APPLICABLE


def test_every_spec_has_an_implementation():
    for t in T:
        inst = Instrument("X", "x", t, Cat.EQUITY_BROAD if t is T.ETF else None, False)
        compute_all(Snapshot(inst, AS_OF))        # raises NotImplementedError if a spec is unwired
