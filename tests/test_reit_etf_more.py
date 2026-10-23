"""Additional instrument-specific synthetic cases: REIT component split with rental income, REIT leverage through the registry,
ETF category applicability matrix, holdings, distributing-ETF caveats, and a missing-data sweep (never OK, never zero)."""
import datetime as dt
from decimal import Decimal as D

import pytest

from irie.calc.distributions import analyze_distributions
from irie.models import (ComponentType as C, ETFCategory as Cat, Holding, Instrument, InstrumentType as T, NavKind,
                         SourceGrade as G)
from irie.registry import SPECS, Snapshot, applicability, compute_all
from irie.result import Status
from tests.helpers import AS_OF, REIT, ev, nav, px

d = dt.date.fromisoformat


def rev(ex, total, comps, **kw):
    return ev(ex, total, comps, key="R", **kw)


def test_reit_five_component_split_reconciles_and_capital_stays_out_of_income():
    comps = {C.INTEREST: "0.2", C.DIVIDEND: "0.1", C.RENTAL: "1.2", C.OTHER_INCOME: "0.05", C.CAPITAL_REPAYMENT: "0.45"}
    a = analyze_distributions(REIT, [rev("2026-08-01", 2.0, comps), rev("2026-05-01", 2.0, comps)], px(100, key="R"), AS_OF)
    m = a.metrics
    assert m["ttm_yield"].value == D("0.04")
    assert m["income_yield"].value == D("0.030") and m["other_yield"].value == D("0.001") and m["capital_repayment_yield"].value == D("0.009")
    assert m["income_share"].value == D("0.75") and m["capital_repayment_share"].value == D("0.225")
    assert m["income_yield"].value + m["other_yield"].value + m["capital_repayment_yield"].value == m["ttm_yield"].value


def test_reit_paying_only_return_of_capital_has_zero_income_not_unavailable():
    a = analyze_distributions(REIT, [rev("2026-08-01", 2.0, {C.CAPITAL_REPAYMENT: "2.0"})], px(100, key="R"), AS_OF)
    assert a.metrics["income_yield"].value == D(0) and a.metrics["income_yield"].ok       # a verified split, income truly 0
    assert a.metrics["capital_repayment_share"].value == D(1)


def test_reit_income_growth_follows_rental_not_total():
    mk = lambda r, k: {C.RENTAL: r, C.CAPITAL_REPAYMENT: k}
    old = [rev("2024-02-01", 1, {C.RENTAL: "1"})]
    prior = [rev("2025-08-01", 3, mk("1.5", "1.5")), rev("2025-02-01", 3, mk("1.5", "1.5"))]
    cur = [rev("2026-08-01", 3, mk("2.4", "0.6")), rev("2026-02-01", 3, mk("2.4", "0.6"))]
    m = analyze_distributions(REIT, old + prior + cur, px(100, key="R"), AS_OF).metrics
    assert m["yoy_total_dpu"].value == D(0) and m["yoy_income_dpu"].value == D("0.6")


def test_reit_net_debt_to_gav_through_the_registry_and_nav_staleness():
    s = Snapshot(REIT, AS_OF, price=px(110, key="R"), nav=nav(100, "2025-12-31", key="R"), net_debt=D(30), gav=D(100))
    out = compute_all(s)
    assert out["net_debt_to_gav"].value == D("0.3") and "LEVERAGE_UNVERIFIED" in out["net_debt_to_gav"].flags
    assert out["premium_to_nav"].value == D("0.1") and "NAV_STALE" in out["premium_to_nav"].flags      # 294 days > 270
    assert out["holdings_top10_weight"].status is Status.NOT_APPLICABLE and out["nav_return_1y"].status is Status.NOT_APPLICABLE


ETF_METRICS = {n for n, sp in SPECS.items() if T.ETF in sp.types}


def etf(cat, distributes=False):
    return Instrument("E", "e", T.ETF, cat, distributes)


@pytest.mark.parametrize("cat,defined", [
    (Cat.EQUITY_BROAD, {"premium_discount_to_nav", "nav_return_1y", "trailing_distribution_yield", "holdings_top10_weight", "tracking_difference_1y"}),
    (Cat.EQUITY_SECTOR_THEMATIC_FACTOR, {"premium_discount_to_nav", "nav_return_1y", "trailing_distribution_yield", "holdings_top10_weight", "tracking_difference_1y"}),
    (Cat.INTERNATIONAL, {"premium_discount_to_nav", "nav_return_1y", "trailing_distribution_yield", "holdings_top10_weight", "tracking_difference_1y"}),
    (Cat.GOLD_SILVER, {"premium_discount_to_nav", "nav_return_1y", "trailing_distribution_yield", "tracking_difference_1y"}),
    (Cat.DEBT, {"premium_discount_to_nav", "nav_return_1y", "trailing_distribution_yield", "holdings_top10_weight"}),
    (Cat.OTHER, {"premium_discount_to_nav", "nav_return_1y", "trailing_distribution_yield"}),
])
def test_etf_category_applicability_matrix_is_pinned(cat, defined):
    got = {n for n in ETF_METRICS if applicability(etf(cat), SPECS[n]) is None}
    assert got == defined, (cat, got ^ defined)
    out = compute_all(Snapshot(etf(cat), AS_OF))
    assert {n for n in ETF_METRICS if out[n].status is not Status.NOT_APPLICABLE or n == "trailing_distribution_yield"} >= defined - {"trailing_distribution_yield"}


def test_debt_etf_gets_holdings_and_no_tracking_difference():
    holdings = [Holding("E", d("2026-09-30"), f"I{i}", f"n{i}", D("0.1"), "S") for i in range(10)]
    navs = [nav(100, "2025-10-21", "E", G.ISSUER, NavKind.FUND_NAV), nav(104, "2026-10-21", "E", G.ISSUER, NavKind.FUND_NAV)]
    out = compute_all(Snapshot(etf(Cat.DEBT), AS_OF, navs=navs, holdings=holdings, benchmark=[(d("2025-10-21"), D(1)), (d("2026-10-21"), D(2))]))
    assert out["holdings_top10_weight"].value == D(1) and out["nav_return_1y"].value == D("0.04")
    assert out["tracking_difference_1y"].status is Status.NOT_APPLICABLE              # a debt fund's lens is YTM/duration, which needs data we do not hold


def test_distributing_etf_is_caveated_and_never_given_a_split():
    inst = etf(Cat.EQUITY_BROAD, True)
    navs = [nav(100, "2025-10-21", "E", G.ISSUER, NavKind.FUND_NAV), nav(110, "2026-10-21", "E", G.ISSUER, NavKind.FUND_NAV)]
    out = compute_all(Snapshot(inst, AS_OF, events=[ev("2026-06-01", 2, key="E")], price=px(100, key="E"), navs=navs))
    assert "EXCLUDES_DISTRIBUTIONS" in out["nav_return_1y"].flags
    y = out["trailing_distribution_yield"]
    assert y.value == D("0.02") and "NO_COMPONENT_SPLIT" in y.flags
    for n in ("income_yield", "capital_repayment_share", "ttm_dpu"):
        assert out[n].status is Status.NOT_APPLICABLE


@pytest.mark.parametrize("inst", [Instrument("T", "t", T.INVIT), Instrument("R", "r", T.REIT), etf(Cat.EQUITY_BROAD), etf(Cat.GOLD_SILVER),
                                  etf(Cat.DEBT, True), etf(None)])
def test_empty_snapshot_never_yields_ok_or_a_zero(inst):
    out = compute_all(Snapshot(inst, AS_OF))
    for n, r in out.items():
        assert r.status is not Status.OK, (inst.type, inst.etf_category, n)
        assert r.value is None, (n, r.value)
        assert r.status is Status.NOT_APPLICABLE or r.reasons, (n, "unavailable without a reason")
