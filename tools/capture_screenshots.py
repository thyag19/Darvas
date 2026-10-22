"""Capture full-page screenshots of every implemented view from the REAL rendered dashboard, using SYNTHETIC demo data.

Usage: python tools/capture_screenshots.py --out artifacts/screenshots/before [--label "before M3"]

Builds the demo site in a temp dir (irie.demo -> ingest cycle -> export), serves it locally, drives Chromium (Playwright)
and writes PNGs plus a README.md inventory. A view whose UI does not exist is listed as NOT IMPLEMENTED; nothing is
mocked. Every screenshot shows invented demo values, never market data.
"""
from __future__ import annotations

import argparse
import dataclasses
import functools
import glob
import http.server
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from irie import demo, export, ingest, site, storage as st  # noqa: E402


def build(tmp: Path, nothing_cleared=False, with_data=True) -> Path:
    inbox = tmp / "inbox"
    demo.write_demo_inbox(inbox)
    conn = st.connect(); st.init_schema(conn)
    reg = demo.demo_registry()
    if nothing_cleared:
        reg = {k: dataclasses.replace(v, display_cleared=False, display_evidence="") for k, v in reg.items()}
    ingest.run_cycle(conn, reg, {k: ingest.FileInboxFetcher(inbox, lambda: demo.DEMO_NOW) for k in reg}, lambda: demo.DEMO_NOW)
    ds = export.build_dataset(conn, reg, demo.DEMO_NOW, "public")
    ds["notice"] = "SYNTHETIC DEMO DATA: invented by irie.demo. Not real market data."
    out = tmp / f"site-{int(nothing_cleared)}-{int(with_data)}"
    site.build_site(export.dumps(ds), out)
    if not with_data:
        (out / "data.json").unlink()
    return out


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(d):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(d)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    tmp = Path(tempfile.mkdtemp())
    site_main, site_closed, site_nodata = build(tmp), build(tmp, True), build(tmp, True, False)
    servers = [serve(site_main), serve(site_closed), serve(site_nodata)]
    inventory = []   # (file or None, title, how, status, note)

    def rec(name, title, how, ok=True, note=""):
        inventory.append((name if ok else None, title, how, "captured" if ok else "NOT IMPLEMENTED", note))

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0],
                                    args=["--no-sandbox"])

        def new(url, w=1440, h=1000, expect_error=False, **kw):
            ctx = browser.new_context(viewport={"width": w, "height": h}, accept_downloads=True, **kw)
            pg = ctx.new_page()
            pg.goto(url)
            pg.wait_for_selector("[data-testid=load-error], #notice:has-text('Could not load')" if expect_error else "[data-testid=row]", timeout=15000)
            pg.wait_for_timeout(300)
            return ctx, pg

        def shot(pg, name, selector=None, full=True):
            path = out / name
            if selector:
                pg.locator(selector).first.screenshot(path=str(path))
            else:
                pg.screenshot(path=str(path), full_page=full)

        has = lambda pg, sel: pg.locator(sel).count() > 0
        url = servers[0][1]
        ctx, pg = new(url)
        shot(pg, "01-dashboard-watchlist-full.png")
        rec("01-dashboard-watchlist-full.png", "Main dashboard: summary cards, filters, watchlist, yield comparison, sources", "Open the site root", note="synthetic demo data")
        shot(pg, "02-summary-cards.png", "[data-testid=cards]")
        rec("02-summary-cards.png", "Summary cards", "Top of the dashboard", note="synthetic")
        shot(pg, "03-watchlist-table.png", "[data-testid=table]")
        rec("03-watchlist-table.png", "Sortable watchlist table", "Table under Filters; click a column header to sort", note="synthetic; shows n/a and withheld states")
        pg.locator("[data-testid=sort-ttm_yield]").click(); pg.locator("[data-testid=sort-ttm_yield]").click()
        shot(pg, "04-watchlist-sorted-yield-desc.png", "[data-testid=table]")
        rec("04-watchlist-sorted-yield-desc.png", "Watchlist sorted by headline yield, descending (unavailable values last)", "Click the 'Headline TTM yield' header twice", note="synthetic")
        pg.locator("[data-testid=row]", has_text="Beta").locator("[data-testid=star]").click()
        pg.check("[data-testid=only-watch]")
        shot(pg, "05-watchlist-starred-only.png", "[data-testid=table]")
        rec("05-watchlist-starred-only.png", "Starred-instruments watchlist filter", "Star a row, tick 'Watchlist only'", note="synthetic")
        ctx.close()

        ctx, pg = new(url)
        pg.select_option("[data-testid=type-filter]", "ETF"); pg.fill("[data-testid=search]", "gold")
        shot(pg, "06-filters-etf-search.png", full=False)
        rec("06-filters-etf-search.png", "Type filter (ETF) plus text search ('gold')", "Choose Type = ETF and type in Search", note="synthetic")
        pg.fill("[data-testid=search]", "no-such-instrument")
        shot(pg, "07-empty-state-no-results.png", full=False)
        rec("07-empty-state-no-results.png", "Empty state for a search with no results", "Search for text that matches nothing", note="synthetic; the current UI shows only an empty table body, no explanatory empty-state message")
        pg.fill("[data-testid=search]", ""); pg.select_option("[data-testid=type-filter]", "ALL")
        with pg.expect_download() as dl:
            pg.click("[data-testid=csv]")
        shutil.copyfile(dl.value.path(), out / "export-sample.csv")
        shot(pg, "08-export-csv-control.png", ".filters")
        rec("08-export-csv-control.png", "CSV export control (filters bar); the downloaded file is saved as export-sample.csv", "Click 'Export CSV'", note="synthetic; a browser download has no page, so the file itself is attached")
        ctx.close()

        ctx, pg = new(url)
        pg.locator("[data-testid=row]", has_text="InvIT Alpha").click()
        pg.wait_for_timeout(200)
        det = "[data-testid=drawer]" if has(pg, "[data-testid=drawer]") else "[data-testid=detail]"
        shot(pg, "09-instrument-detail-invit.png", det)
        rec("09-instrument-detail-invit.png", "Instrument detail (InvIT): distribution history with component split, price and NAV history, metrics table", "Click any watchlist row", note="synthetic")
        pg.locator("[data-testid=row]", has_text="REIT Alpha").click()
        pg.wait_for_timeout(200)
        shot(pg, "10-instrument-detail-reit-discrepancy.png", det)
        rec("10-instrument-detail-reit-discrepancy.png", "Instrument detail (REIT) showing an open cross-source discrepancy and withheld figures", "Click the REIT row", note="synthetic discrepancy created by irie.demo")
        pg.locator("[data-testid=row]", has_text="Equity Index ETF").click()
        pg.wait_for_timeout(200)
        shot(pg, "11-instrument-detail-etf.png", det)
        rec("11-instrument-detail-etf.png", "Instrument detail (ETF): NAV history, premium/discount, NAV return; no income/capital split", "Click the ETF row", note="synthetic")
        ctx.close()

        ctx, pg = new(url)
        shot(pg, "12-yield-comparison.png", "[data-testid=yield-chart]")
        rec("12-yield-comparison.png", "Yield comparison chart grouped by instrument type", "Section 'Yield comparison'", note="synthetic")
        ctx.close()

        ctx, pg = new(url)
        pg.select_option("[data-testid=alert-type]", "yield_above"); pg.fill("[data-testid=alert-value]", "5")
        pg.click("[data-testid=alert-add]")
        pg.select_option("[data-testid=alert-type]", "discount_below"); pg.fill("[data-testid=alert-value]", "-50")
        pg.click("[data-testid=alert-add]")
        pg.evaluate("window.scrollTo(0, 0)")
        shot(pg, "13-alerts-inline-form-and-triggered.png")
        rec("13-alerts-inline-form-and-triggered.png", "Alerts: inline form, configured triggers and triggered banner (current UI has no modal Alert Center)", "Scroll to 'Alerts' and add a rule", note="synthetic")
        rec(None, "Alert Center modal with timestamps and sound selection", "-", ok=False, note="current UI: alert form is inline, no per-alert timestamps, no TRIGGERED state, no sound")
        ctx.close()

        ctx, pg = new(url)
        shot(pg, "14-sources-freshness.png", "[data-testid=sources]")
        rec("14-sources-freshness.png", "Data sources and freshness table (access status, display-cleared, freshness, last attempt, observed-through)", "Bottom of the page", note="synthetic demo sources only")
        ctx.close()

        ctx, pg = new(servers[1][1])
        shot(pg, "15-data-quality-nothing-cleared.png")
        rec("15-data-quality-nothing-cleared.png", "Public build when no source is cleared for display: every value withheld", "Build with display_cleared=false", note="synthetic; demonstrates the licence gate")
        ctx.close()

        ctx, pg = new(url, 390, 844)
        shot(pg, "16-mobile-390px-full.png")
        rec("16-mobile-390px-full.png", "Mobile layout (390 px wide)", "Narrow viewport", note="synthetic")
        ctx.close()

        ctx, pg = new(servers[2][1], expect_error=True)
        shot(pg, "17-error-state-data-missing.png", full=False)
        rec("17-error-state-data-missing.png", "Error state when data.json cannot be loaded", "Serve the site without data.json", note="synthetic site, data file removed")
        ctx.close()

        ctx, pg = new(url)
        for tid, title in (("news-panel", "Live news feed and scrip announcements panel"),
                           ("hours-badge", "Market-hours / refresh-schedule status"),
                           ("theme-toggle", "Light/dark theme switch")):
            if has(pg, f"[data-testid={tid}]"):
                nm = {"news-panel": "18-news-panel.png", "hours-badge": "19-market-status.png", "theme-toggle": "20-dark-theme.png"}[tid]
                if tid == "theme-toggle":
                    pg.click("[data-testid=theme-toggle]"); pg.wait_for_timeout(200); shot(pg, nm)
                else:
                    shot(pg, nm, f"[data-testid={tid}]")
                rec(nm, title, f"data-testid={tid}", note="synthetic")
            else:
                rec(None, title, "-", ok=False, note="no such UI in this build")
        ctx.close()
        browser.close()
    for s, _ in servers:
        s.shutdown()

    lines = [f"# Screenshots {a.label}".rstrip(), "",
             "Rendered by real Chromium from the dashboard in this repository, using **synthetic demo data only** (`irie/demo.py`). "
             "Every name, price, yield and date is invented; none of it is market data. Regenerate with "
             "`python tools/capture_screenshots.py --out <dir>`.", "",
             "| File | View | How to reach it | Status | Notes |", "|---|---|---|---|---|"]
    for f, title, how, status, note in inventory:
        lines.append(f"| {('`' + f + '`') if f else '-'} | {title} | {how} | {status} | {note} |")
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{sum(1 for i in inventory if i[0])} captured, {sum(1 for i in inventory if not i[0])} not implemented -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
