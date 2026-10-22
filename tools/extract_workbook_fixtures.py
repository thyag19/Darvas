"""One-off, read-only extraction of regression fixtures from InvIT_Yield_Analysis_Tool_v4.xlsx.

Usage: python tools/extract_workbook_fixtures.py <workbook.xlsx> <output_dir>

The workbook is opened read-only (never saved). Values are the workbook's cached results, so the
fixtures pin what the audited workbook produced; the tests recompute them independently.
No network access. Output is deterministic for a given workbook.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import openpyxl

AS_OF = dt.date(2026, 10, 21)


def num(v):
    return "" if v is None else repr(round(v, 10)) if isinstance(v, float) else str(v)


def d(v):
    return "" if v is None else v.date().isoformat() if isinstance(v, dt.datetime) else str(v)


def amount_grade(status: str) -> str:
    """Mirror the workbook's own 'Verified' rule (DISTRIBUTION HISTORY!R): exchange- or issuer-verified."""
    s = status or ""
    if s.startswith("Exchange-verified"):
        return "EXCHANGE"
    if s.startswith("Issuer-verified") or "Issuer website" in s:
        return "ISSUER"
    return "AGGREGATOR"


def source_grade(g: str) -> str:
    g = (g or "").lower()
    if g.startswith("exchange"):
        return "EXCHANGE"
    if g.startswith("issuer"):
        return "ISSUER"
    if g.startswith("regulator"):
        return "REGULATOR"
    if g.startswith("aggregator"):
        return "AGGREGATOR"
    return "UNKNOWN"


def write(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def main(xlsx: str, out: str) -> None:
    raw = Path(xlsx).read_bytes()
    wb = openpyxl.load_workbook(xlsx, data_only=True, read_only=False)
    outd = Path(out)
    outd.mkdir(parents=True, exist_ok=True)

    uni = wb["UNIVERSE AUDIT"]
    write(outd / "instruments.csv",
          ["key", "name", "type", "etf_category", "distributes", "isin", "nse_symbol", "bse_symbol", "bse_scrip"],
          [[uni.cell(r, 2).value, uni.cell(r, 3).value, "INVIT", "", "", uni.cell(r, 7).value,
            uni.cell(r, 4).value, uni.cell(r, 5).value, uni.cell(r, 6).value] for r in range(29, 55)])

    src = wb["SOURCES AND ASSUMPTIONS"]
    write(outd / "sources.csv", ["source_id", "name", "url", "grade", "comment"],
          [[src.cell(r, 1).value, src.cell(r, 2).value, src.cell(r, 3).value or "",
            source_grade(src.cell(r, 5).value), src.cell(r, 6).value or ""] for r in range(18, 32)])

    dh = wb["DISTRIBUTION HISTORY"]
    rows = []
    for r in range(37, 715):
        if not dh.cell(r, 1).value:
            continue
        g = lambda c: dh.cell(r, c).value
        rows.append([g(1), d(g(3)), d(g(4)), g(5) or "", num(g(6)), num(g(7)), num(g(8)), "", num(g(9)), num(g(10)),
                     g(11), amount_grade(g(13)), g(12), g(13) or "", g(17) or ""])
    write(outd / "distributions.csv",
          ["instrument_key", "ex_date", "record_date", "period_label", "total_per_unit", "interest", "dividend",
           "rental", "other_income", "capital_repayment", "include", "amount_grade", "source_id", "status_text", "notes"],
          rows)

    sc = wb["INVIT SCREENER"]
    snap, exp = [], []
    for r in range(6, 32):
        g = lambda c: sc.cell(r, c).value
        snap.append([g(1), num(g(6)), d(g(7)), g(8) or "", num(g(11)), num(g(13)), d(g(14)), g(15) or "",
                     num(g(18)), d(g(19)), g(20) or "", g(21) or "", g(24)])
        exp.append([g(1), g(5), g(10), num(g(17)), num(g(30)), num(g(31)), num(g(33)), num(g(34)), num(g(35)),
                    num(g(36)), num(g(37)), num(g(38)), num(g(39)), g(40), num(g(41)), num(g(42)), num(g(43)),
                    num(g(44)), g(45), num(g(58)), num(g(59)), num(g(60)), num(g(61))])
    write(outd / "snapshot.csv",
          ["key", "price", "price_date", "price_venue", "units_crore", "nav", "nav_date", "nav_status",
           "gearing", "gearing_date", "gearing_status", "gearing_definition", "workbook_source_grade"], snap)
    write(outd / "expected_screener.csv",
          ["key", "trading_class", "price_status", "premium_to_nav", "ttm_dpu", "ttm_yield", "headline_yield",
           "income_yield", "other_yield", "capital_yield", "income_share", "other_share", "capital_share",
           "component_status", "payments_ttm", "yoy", "cv", "largest_share", "history_check",
           "ttm_interest", "ttm_dividend", "ttm_other", "ttm_capital"], exp)

    tr = wb["TOTAL RETURN"]
    lots = [[tr.cell(r, 3).value, d(tr.cell(r, 4).value), num(tr.cell(r, 5).value), num(tr.cell(r, 6).value),
             num(tr.cell(r, 7).value)] for r in range(10, 30) if tr.cell(r, 3).value and tr.cell(r, 5).value]
    write(outd / "lots.csv", ["instrument_key", "purchase_date", "units", "price_paid", "charges"], lots)
    flows = [[d(tr.cell(r, 24).value), num(tr.cell(r, 25).value)] for r in range(10, 710)
             if isinstance(tr.cell(r, 25).value, (int, float)) and tr.cell(r, 25).value != 0]
    write(outd / "xirr_flows.csv", ["date", "flow"], flows)
    (outd / "expected_portfolio.json").write_text(json.dumps({
        "total_cost": tr["H30"].value, "market_value": tr["J30"].value, "distributions": tr["L30"].value,
        "capital_repayment_received": tr["M30"].value, "xirr": tr["B41"].value,
        "xirr_note": "Excel XIRR; converges to ~1e-8, so tests use a 1e-7 tolerance",
    }, indent=2, sort_keys=True) + "\n")

    (outd / "meta.json").write_text(json.dumps({
        "as_of": AS_OF.isoformat(),
        "source_workbook": "InvIT_Yield_Analysis_Tool_v4.xlsx",
        "source_workbook_sha256": hashlib.sha256(raw).hexdigest(),
        "distribution_rows": len(rows),
        "note": "Seed/regression data copied from the user-supplied workbook. Provenance is unverified "
                "(audit/evidence was not supplied) and display licensing is NOT cleared for any source.",
    }, indent=2, sort_keys=True) + "\n")
    print(f"wrote fixtures to {outd}: {len(rows)} distribution rows")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
