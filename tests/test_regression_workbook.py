"""Independent reproduction of the audited workbook (INVIT SCREENER cached values, 26 trusts, as of 21-Oct-2026).

The engine recomputes everything from the 398 raw distribution rows; the workbook's cached results are the
expected values. This proves the formulas, not the inputs (see docs)."""
import csv
import datetime as dt
import json
from decimal import Decimal

import pytest

from irie.calc.distributions import Coverage, HistoryCheck, analyze_distributions
from irie.calc.returns import Lot, portfolio_ledger, xirr
from irie.registry import Snapshot, compute_all
from irie.result import Status
from tests.conftest import BUNDLE_DIR

pytestmark = pytest.mark.usefixtures("fixtures_present")
TOL = Decimal("1e-9")


def dec(s):
    return None if s in ("", None) else Decimal(s)


def snap(bundle, key, as_of):
    return Snapshot(bundle.instruments[key], as_of, [e for e in bundle.events if e.instrument_key == key],
                    bundle.prices.get(key), bundle.navs.get(key), leverage=bundle.leverage.get(key))


def close(a, b):
    return abs(a - b) <= TOL


def test_seed_import_is_clean(bundle):
    s = bundle.report.summary()
    assert s["rows_read"] == 398 and s["accepted"] == 398 and s["rejected"] == 0
    assert len(bundle.instruments) == 26


@pytest.fixture(scope="module")
def results(bundle, as_of):
    return {k: compute_all(snap(bundle, k, as_of)) for k in bundle.instruments}


def test_ttm_dpu_payments_and_yield(results, expected, bundle):
    for key, exp in expected.items():
        r = results[key]
        if exp["ttm_dpu"] == "n/a":
            assert r["ttm_dpu"].status is Status.UNAVAILABLE and r["ttm_dpu"].value is None, key
            assert r["payments_ttm"].value is None, key
        else:
            assert close(r["ttm_dpu"].value, dec(exp["ttm_dpu"])), key
            assert r["payments_ttm"].value == Decimal(exp["payments_ttm"]), key
        for col in ("ttm_yield",):
            if exp["ttm_yield"] in ("n/a", "N/A"):
                assert not r["ttm_yield"].ok, key
            else:
                assert close(r["ttm_yield"].value, dec(exp["ttm_yield"])), key
        if exp["headline_yield"] not in ("n/a", "N/A"):
            assert close(r["ttm_yield"].value, dec(exp["headline_yield"])), key


def test_component_yields_and_shares_complete_only(results, expected):
    complete_with_yield = 0
    for key, exp in expected.items():
        r = results[key]
        complete = exp["component_status"].startswith("COMPLETE")
        if complete:  # shares do not depend on price
            assert close(r["income_share"].value, dec(exp["income_share"])), key
            assert close(r["other_share"].value, dec(exp["other_share"])), key
            assert close(r["capital_repayment_share"].value, dec(exp["capital_share"])), key
            if exp["income_yield"] == "N/A":  # no usable price
                assert r["income_yield"].value is None and "PRICE_MISSING" in r["income_yield"].reasons, key
            else:
                complete_with_yield += 1
                assert close(r["income_yield"].value, dec(exp["income_yield"])), key
                assert close(r["other_yield"].value, dec(exp["other_yield"])), key
                assert close(r["capital_repayment_yield"].value, dec(exp["capital_yield"])), key
        else:
            # N/A or PARTIAL in the workbook => withheld here, never zero
            for n in ("income_yield", "other_yield", "capital_repayment_yield", "capital_repayment_share"):
                assert r[n].value is None and r[n].status in (Status.UNAVAILABLE, Status.PARTIAL), (key, n)
    assert complete_with_yield == 19  # 21 COMPLETE trusts; 2 of them have no usable price


def test_split_adds_up_to_headline_where_complete(results):
    for key, r in results.items():
        if r["income_yield"].ok and r["ttm_yield"].ok:
            total = r["income_yield"].value + r["other_yield"].value + r["capital_repayment_yield"].value
            assert abs(total - r["ttm_yield"].value) < Decimal("0.001"), key  # per-record rounding tolerance
            assert abs(r["income_share"].value + r["other_share"].value + r["capital_repayment_share"].value - 1) < Decimal("0.001")


def test_yoy_cv_largest_and_history(results, expected):
    mapping = {"OK": HistoryCheck.OK, "Incomplete: history starts": HistoryCheck.SHORT_HISTORY,
               "No amounts": HistoryCheck.NO_AMOUNTS, "No data": HistoryCheck.NO_DATA,
               "Incomplete: ": HistoryCheck.UNAVAILABLE_AMOUNTS}
    for key, exp in expected.items():
        r = results[key]
        if exp["yoy"] in ("n/a", ""):
            assert r["yoy_total_dpu"].value is None, key
        else:
            assert close(r["yoy_total_dpu"].value, dec(exp["yoy"])), key
        if exp["cv"] in ("n/a", ""):
            assert r["payment_size_cv"].value is None, key
        else:
            assert close(r["payment_size_cv"].value, dec(exp["cv"])), key
        if exp["largest_share"] not in ("n/a", ""):
            assert close(r["largest_payment_share"].value, dec(exp["largest_share"])), key


def test_history_check_matches_workbook(bundle, expected, as_of):
    for key, exp in expected.items():
        a = analyze_distributions(bundle.instruments[key], bundle.events, bundle.prices.get(key), as_of)
        h = exp["history_check"]
        want = (HistoryCheck.OK if h == "OK" else HistoryCheck.SHORT_HISTORY if h.startswith("Incomplete: history starts")
                else HistoryCheck.NO_AMOUNTS if h.startswith("No amounts") else HistoryCheck.NO_DATA if h == "No data"
                else HistoryCheck.UNAVAILABLE_AMOUNTS)
        assert a.history is want, (key, h, a.history)


def test_premium_to_nav(results, expected):
    for key, exp in expected.items():
        r = results[key]["premium_to_nav"]
        if exp["premium_to_nav"] in ("n/a", ""):
            assert not r.ok, key
        else:
            assert close(r.value, dec(exp["premium_to_nav"])), key


def test_stale_price_is_flagged_not_hidden(results, expected):
    for key, exp in expected.items():
        r = results[key]["ttm_yield"]
        if exp["price_status"] == "STALE" and r.ok:
            assert "PRICE_STALE" in r.flags, key
    assert "PRICE_STALE" in results["INTERISE"]["ttm_yield"].flags


# ---- Phase 1 defects, pinned against the real data --------------------------------------------------------

def test_C1_aggregator_sourced_trusts_are_flagged_blocking(bundle, results):
    flagged = {k for k, r in results.items() if "UNVERIFIED_SOURCE" in r["ttm_dpu"].flags}
    workbook_aggregator = {k for k, g in bundle.workbook_source_grade.items() if g == "Aggregator"}
    assert flagged == workbook_aggregator == {"ALTIUS", "EIT"}


def test_C2_split_or_reason_always_present(results):
    for key, r in results.items():
        if r["ttm_yield"].ok:
            cap = r["capital_repayment_yield"]
            assert cap.ok or cap.reasons, key  # a headline yield never travels without split-or-reason
    assert results["ALTIUS"]["capital_repayment_yield"].reasons == ("COMPONENTS_NONE",)


def test_C5_unavailable_is_never_zero(results):
    for key in ("MAPLE", "ISCIT", "DIGIFIBRE"):
        for n in ("ttm_dpu", "ttm_yield", "income_yield", "capital_repayment_yield"):
            assert results[key][n].value is None, (key, n)
        assert results[key]["ttm_dpu"].reasons == ("ALL_AMOUNTS_UNAVAILABLE_IN_WINDOW",), key
    for key in ("OSEINTRUST", "IRBIT", "DIGIFIBRE"):  # no usable price
        assert results[key]["ttm_yield"].value is None and "PRICE_MISSING" in results[key]["ttm_yield"].reasons


def test_C7_growth_on_income_is_separate_from_total(results):
    assert all("INCLUDES_CAPITAL_REPAYMENT" in r["yoy_total_dpu"].flags for r in results.values() if r["yoy_total_dpu"].ok)


def test_no_score_rank_or_tax_metric_exists(results):
    names = set(next(iter(results.values())))
    assert not any(w in n for n in names for w in ("score", "rank", "tax", "forward"))


def test_import_flags_known_ambiguities(bundle):
    codes = bundle.report.codes()
    assert codes["SAME_EX_DATE_MULTIPLE_RECORDS"] == 2           # CAPINVIT 2025-06-03 (Rs 11.18 and Rs 2.61)
    assert codes["UNVERIFIED_AMOUNT_SOURCE"] > 0
    capinvit = [i for i in bundle.report.issues if i.code == "SAME_EX_DATE_MULTIPLE_RECORDS"]
    assert {bundle.report.raw[i.row]["instrument_key"] for i in capinvit} == {"CAPINVIT"}


# ---- returns ---------------------------------------------------------------------------------------------

def test_xirr_reproduces_workbook_flows():
    exp = json.loads((BUNDLE_DIR / "expected_portfolio.json").read_text())
    with (BUNDLE_DIR / "xirr_flows.csv").open(newline="") as f:
        flows = [(dt.date.fromisoformat(r["date"]), Decimal(r["flow"])) for r in csv.DictReader(f)]
    assert len(flows) == 35
    assert abs(xirr(flows) - exp["xirr"]) < 1e-7   # Excel's XIRR is only accurate to ~1e-8


def test_portfolio_ledger_reproduces_workbook(bundle, as_of):
    exp = json.loads((BUNDLE_DIR / "expected_portfolio.json").read_text())
    with (BUNDLE_DIR / "lots.csv").open(newline="") as f:
        lots = [Lot(r["instrument_key"], dt.date.fromisoformat(r["purchase_date"]), Decimal(r["units"]),
                    Decimal(r["price_paid"]), Decimal(r["charges"])) for r in csv.DictReader(f)]
    led = portfolio_ledger(lots, bundle.events, bundle.prices, as_of)
    assert led.total_cost == Decimal(str(exp["total_cost"]))
    assert led.market_value == Decimal(str(exp["market_value"]))
    assert abs(led.distributions - Decimal(str(exp["distributions"]))) < Decimal("1e-6")
    assert abs(led.capital_repayment_received - Decimal(str(exp["capital_repayment_received"]))) < Decimal("1e-6")
    assert abs(xirr(led.flows) - exp["xirr"]) < 1e-7
    assert not led.lots_without_price


def test_known_limit_fixture_is_insensitive_to_a_one_day_window_change(bundle, as_of):
    """No fixture event sits within a day of a window edge, so the regression alone cannot detect an off-by-one
    window length. Boundary behaviour is pinned by the synthetic tests in test_distributions.py instead."""
    edges = {as_of - dt.timedelta(days=n) for n in (364, 365, 366, 729, 730, 731)}
    assert not [e for e in bundle.events if e.ex_date in edges]
