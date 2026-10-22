"""Synthetic edge cases for the shared REIT/InvIT distribution engine."""
import datetime as dt
from decimal import Decimal as D

import pytest

from irie.calc.distributions import (Coverage, HistoryCheck, analyze_distributions, component_status,
                                     ComponentStatus)
from irie.models import ComponentType as C, SourceGrade as G
from irie.result import Status
from tests.helpers import AS_OF, INVIT, REIT, ev, px

OLD = [ev("2024-01-15", 1), ev("2024-04-15", 1)]  # history older than the prior window start (2024-10-21)
LONG = [ev("2024-02-01", 1)]


def run(events, price=None, inst=INVIT, **kw):
    return analyze_distributions(inst, events, price or px(100), AS_OF, **kw)


def test_ttm_window_boundaries_are_exclusive_start_inclusive_end():
    start = AS_OF - dt.timedelta(days=365)
    a = run([ev(start.isoformat(), 5), ev(AS_OF.isoformat(), 2), ev((start + dt.timedelta(days=1)).isoformat(), 1)])
    assert a.metrics["ttm_dpu"].value == D(3)          # start excluded, as_of included
    assert a.metrics["payments_ttm"].value == 2
    assert a.prior.total == D(5)                        # the start date falls in the prior window instead


def test_future_ex_date_is_outside_every_window():
    a = run([ev("2026-10-22", 9), ev("2026-08-01", 1)])
    assert a.metrics["ttm_dpu"].value == D(1)


def test_no_distributions_is_unavailable_not_zero():
    a = run([ev("2024-01-01", 1)])
    m = a.metrics["ttm_dpu"]
    assert m.status is Status.UNAVAILABLE and m.value is None and m.reasons == ("NO_TTM_DISTRIBUTIONS",)
    assert a.metrics["ttm_yield"].value is None


def test_all_amounts_unavailable_never_becomes_zero():
    a = run([ev("2026-08-01", None, include=False), ev("2026-05-01", None, include=False)])
    assert a.metrics["ttm_dpu"].reasons == ("ALL_AMOUNTS_UNAVAILABLE_IN_WINDOW",)
    assert a.history is HistoryCheck.NO_AMOUNTS


def test_partial_unavailable_amount_gives_lower_bound_with_blocking_flag():
    a = run([ev("2026-08-01", 2), ev("2026-05-01", None, include=False)])
    m = a.metrics["ttm_dpu"]
    assert m.value == D(2) and "AMOUNT_UNAVAILABLE_IN_WINDOW" in m.flags
    assert a.metrics["yoy_total_dpu"].value is None


def test_excluded_duplicate_with_amount_is_ignored_silently_and_not_counted_unavailable():
    a = run([ev("2026-08-01", 2), ev("2026-08-02", 2, include=False)])
    assert a.metrics["ttm_dpu"].value == D(2) and not a.metrics["ttm_dpu"].flags


def test_headline_yield_and_split_complete():
    e = [ev("2026-08-01", 3, {C.INTEREST: "2", C.DIVIDEND: "0.5", C.CAPITAL_REPAYMENT: "0.5"}),
         ev("2026-05-01", 3, {C.INTEREST: "2.5", C.OTHER_INCOME: "0.5"})]
    a = run(e, px(100))
    m = a.metrics
    assert m["ttm_yield"].value == D("0.06")
    assert m["income_yield"].value == D("0.050") and m["other_yield"].value == D("0.005")
    assert m["capital_repayment_yield"].value == D("0.005")   # 0.5 / 100
    assert m["capital_repayment_share"].value == D(1) / D(12)
    assert a.ttm.coverage is Coverage.COMPLETE


def test_complete_split_with_no_capital_component_gives_zero_capital_not_unavailable():
    a = run([ev("2026-08-01", 3, {C.INTEREST: "3"})])
    assert a.metrics["capital_repayment_yield"].value == D(0) and a.metrics["capital_repayment_yield"].ok


def test_components_that_do_not_reconcile_are_flagged_and_split_withheld():
    a = run([ev("2026-08-01", 3, {C.INTEREST: "2", C.CAPITAL_REPAYMENT: "0.5"})])   # sums to 2.5, not 3
    assert a.ttm.coverage is Coverage.NONE
    assert a.metrics["income_yield"].value is None and a.metrics["income_yield"].reasons == ("COMPONENTS_NONE",)
    assert "COMPONENTS_DO_NOT_RECONCILE" in a.metrics["ttm_dpu"].flags
    assert a.metrics["ttm_yield"].ok                     # headline stays, the split is never invented


@pytest.mark.parametrize("diff,expected", [("0.0051", ComponentStatus.RECONCILES),
                                           ("0.0052", ComponentStatus.DOES_NOT_RECONCILE)])
def test_reconciliation_tolerance_edge(diff, expected):
    e = ev("2026-08-01", D("3") + D(diff), {C.INTEREST: "3"})
    assert component_status(e) is expected


def test_partial_coverage_withholds_with_partial_status():
    e = [ev("2026-08-01", 3, {C.INTEREST: "3"}), ev("2026-05-01", 3)]   # second has no disclosed components
    a = run(e)
    assert a.ttm.coverage is Coverage.PARTIAL
    assert a.metrics["income_yield"].status is Status.PARTIAL and a.metrics["income_yield"].value is None


def test_components_from_unverified_source_are_not_trusted():
    e = [ev("2026-08-01", 3, {C.INTEREST: "3"}, grade=G.AGGREGATOR)]
    a = run(e)
    assert a.ttm.coverage is Coverage.NONE
    assert "UNVERIFIED_SOURCE" in a.metrics["ttm_yield"].flags


def test_price_rules():
    e = [ev("2026-08-01", 3)]
    assert run(e, px(100, "2026-10-22")).metrics["ttm_yield"].reasons[0].startswith("PRICE_AFTER_AS_OF")
    assert run(e, px(0)).metrics["ttm_yield"].reasons == ("PRICE_NOT_POSITIVE",)
    assert "PRICE_STALE" in run(e, px(100, "2026-10-10")).metrics["ttm_yield"].flags
    assert analyze_distributions(INVIT, e, None, AS_OF).metrics["ttm_yield"].reasons == ("PRICE_MISSING",)
    assert "PRICE_STALE" not in run(e, px(100, "2026-10-18")).metrics["ttm_yield"].flags   # exactly 3 days is fresh


def test_yoy_requires_long_history_and_clean_amounts():
    ttm = [ev("2026-08-01", 4), ev("2026-02-01", 4)]
    prior = [ev("2025-08-01", 2), ev("2025-02-01", 2)]
    short = run(prior + ttm)                              # first record 2025-02-01 is after 2024-10-21
    assert short.history is HistoryCheck.SHORT_HISTORY and short.metrics["yoy_total_dpu"].value is None
    full = run(LONG + prior + ttm)
    assert full.history is HistoryCheck.OK and full.metrics["yoy_total_dpu"].value == D(1)   # 8/4 - 1
    assert "INCLUDES_CAPITAL_REPAYMENT" in full.metrics["yoy_total_dpu"].flags
    gap = run(LONG + prior + ttm + [ev("2025-05-01", None, include=False)])
    assert gap.history is HistoryCheck.UNAVAILABLE_AMOUNTS and gap.metrics["yoy_total_dpu"].value is None
    assert run(LONG + prior + ttm, manual_partial=True).history is HistoryCheck.MANUAL_PARTIAL


def test_income_growth_excludes_capital_repayment_swing():
    c = lambda i, k: {C.INTEREST: i, C.CAPITAL_REPAYMENT: k}
    prior = [ev("2025-08-01", 4, c("2", "2")), ev("2025-02-01", 4, c("2", "2"))]
    ttm = [ev("2026-08-01", 4, c("3", "1")), ev("2026-02-01", 4, c("3", "1"))]
    a = run(LONG + prior + ttm)
    assert a.metrics["yoy_total_dpu"].value == D(0)                     # total flat...
    assert a.metrics["yoy_income_dpu"].value == D("0.5")                # ...income up 50%


def test_income_growth_unavailable_without_components():
    a = run(LONG + [ev("2025-08-01", 2), ev("2026-08-01", 3)])
    assert a.metrics["yoy_income_dpu"].value is None


def test_cv_and_largest_share():
    a = run([ev("2026-08-01", 1), ev("2026-05-01", 2), ev("2026-02-01", 3)])
    assert a.metrics["payment_size_cv"].value == D(1) / D(2)            # stdev 1 / mean 2
    assert a.metrics["largest_payment_share"].value == D(3) / D(6)
    one = run([ev("2026-08-01", 1)])
    assert one.metrics["payment_size_cv"].value is None


def test_reit_rental_counts_as_income_and_invit_rejects_rental():
    e = [ev("2026-08-01", 4, {C.RENTAL: "3", C.CAPITAL_REPAYMENT: "1"}, key="R")]
    a = analyze_distributions(REIT, e, px(100, key="R"), AS_OF)
    assert a.metrics["income_yield"].value == D("0.03") and a.metrics["capital_repayment_yield"].value == D("0.01")
    with pytest.raises(ValueError, match="not allowed"):
        analyze_distributions(INVIT, [ev("2026-08-01", 4, {C.RENTAL: "4"})], px(100), AS_OF)


def test_etf_is_refused_by_the_reit_invit_engine():
    from irie.models import Instrument, InstrumentType
    with pytest.raises(ValueError):
        analyze_distributions(Instrument("E", "e", InstrumentType.ETF), [], None, AS_OF)


def test_engine_is_deterministic():
    e = [ev("2026-08-01", 3, {C.INTEREST: "3"}), ev("2026-05-01", 2.5, {C.INTEREST: "2.5"})]
    assert run(e).metrics == run(list(reversed(e))).metrics
