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

from irie import demo, export, ingest, site, storage as st
from irie.market_calendar import load_calendar
CAL = load_calendar(Path(__file__).resolve().parent.parent / 'config' / 'market_calendar.json')  # noqa: E402


def build(tmp: Path, nothing_cleared=False, with_data=True) -> Path:
    inbox = tmp / "inbox"
    demo.write_demo_inbox(inbox)
    conn = st.connect(); st.init_schema(conn)
    reg = demo.demo_registry()
    if nothing_cleared:
        reg = {k: dataclasses.replace(v, display_cleared=False, display_evidence="") for k, v in reg.items()}
    ingest.run_cycle(conn, reg, {k: ingest.FileInboxFetcher(inbox, lambda: demo.DEMO_NOW) for k in reg}, lambda: demo.DEMO_NOW, calendar=CAL)
    ds = export.build_dataset(conn, reg, demo.DEMO_NOW, "public", CAL)
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
            pg.wait_for_selector("[data-testid=load-error]" if expect_error else "[data-testid=row]", timeout=15000)
            pg.wait_for_timeout(300)
            return ctx, pg

        def shot(pg, name, selector=None, full=True):
            path = out / name
            if selector:
                pg.locator(selector).first.screenshot(path=str(path))
            else:
                if full:
                    pg.evaluate("window.scrollTo({top: 0, behavior: 'instant'})"); pg.wait_for_timeout(120)
                pg.screenshot(path=str(path), full_page=full)

        def tall(pg, name, selector):
            """Element screenshot of a scrolling dialog at its full content height."""
            pg.evaluate(f"(() => {{ const e = document.querySelector('{selector}'); e.style.height = 'auto'; e.style.maxHeight = 'none'; }})()")
            shot(pg, name, selector)

        def close_drawer(pg):
            pg.keyboard.press("Escape"); pg.wait_for_timeout(100)

        url = servers[0][1]
        ctx, pg = new(url)
        shot(pg, "01-dashboard-full-light.png")
        rec("01-dashboard-full-light.png", "Whole dashboard (light theme): header, summary cards, watchlist, yield comparison, news, sources", "Open the site root", note="synthetic demo data")
        pg.screenshot(path=str(out / "02-header-market-status-alerts-theme.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 64})
        rec("02-header-market-status-alerts-theme.png", "Header: navigation, NSE/BSE market-status badge (with 'calendar unverified'), Alerts button, theme switch", "Top of any page", note="synthetic; the calendar flag is real: the shipped 2026 holidays are unverified")
        shot(pg, "03-summary-cards.png", "[data-testid=cards]")
        rec("03-summary-cards.png", "Summary cards", "Under the header", note="synthetic")
        shot(pg, "04-watchlist-table.png", "[data-testid=table]")
        rec("04-watchlist-table.png", "Watchlist table with n/a and withheld states", "Watchlist section", note="synthetic")
        pg.locator("[data-testid=sort-ttm_yield]").click(); pg.locator("[data-testid=sort-ttm_yield]").click()
        shot(pg, "05-watchlist-sorted-yield-desc.png", "[data-testid=table]")
        rec("05-watchlist-sorted-yield-desc.png", "Sorted by headline yield, descending; unavailable values last (a display sort, not a ranking)", "Click 'Headline TTM yield' twice", note="synthetic")
        pg.locator("[data-testid=row]", has_text="Beta").locator("[data-testid=star]").click(); pg.check("[data-testid=only-watch]")
        shot(pg, "06-watchlist-starred-only.png", "#watchlist")
        rec("06-watchlist-starred-only.png", "Starred-only filter", "Star a row, tick 'Starred only'", note="synthetic")
        ctx.close()

        ctx, pg = new(url)
        pg.select_option("[data-testid=type-filter]", "ETF"); pg.fill("[data-testid=search]", "gold")
        shot(pg, "07-filters-etf-search.png", "#watchlist")
        rec("07-filters-etf-search.png", "Type filter (ETF) plus text search ('gold')", "Type = ETF; search box", note="synthetic")
        pg.fill("[data-testid=search]", "no-such-instrument")
        shot(pg, "08-empty-state-no-results.png", "#watchlist")
        rec("08-empty-state-no-results.png", "Empty state with a 'Clear filters' action", "Search for text that matches nothing", note="synthetic")
        pg.fill("[data-testid=search]", ""); pg.select_option("[data-testid=type-filter]", "ALL")
        with pg.expect_download() as dl:
            pg.click("[data-testid=csv]")
        shutil.copyfile(dl.value.path(), out / "export-sample.csv")
        shot(pg, "09-export-csv-control.png", ".toolbar")
        rec("09-export-csv-control.png", "Filter toolbar with the Export CSV control; the downloaded file is attached as export-sample.csv", "Click 'Export CSV'", note="synthetic; a browser download has no page, so the file is attached")
        ctx.close()

        ctx, pg = new(url)
        for key, name, title, note in (("InvIT Alpha", "10-drawer-invit.png", "Detail drawer (InvIT): price and headline-yield trend, distribution per payment, component cards (interest, dividend, return of capital), metrics with status and flags", "synthetic"),
                                       ("REIT Alpha", "11-drawer-reit-discrepancy.png", "Detail drawer (REIT): rental-income component, open cross-source discrepancy, withheld figures, related announcement", "synthetic discrepancy created by irie.demo"),
                                       ("Equity Index ETF", "12-drawer-etf-holdings.png", "Detail drawer (ETF): NAV history, premium/discount, top-10 holdings; no income/capital split exists for an ETF", "synthetic"),
                                       ("InvIT Beta", "13-drawer-split-unavailable.png", "Detail drawer where components are not disclosed: the split is explained as unavailable, never estimated", "synthetic")):
            pg.locator("[data-testid=row]", has_text=key).click(); pg.wait_for_timeout(250)
            tall(pg, name, "[data-testid=drawer]")
            rec(name, title, "Click the watchlist row (Enter works too)", note=note)
            close_drawer(pg)
        shot(pg, "14-yield-comparison.png", "#compare")
        rec("14-yield-comparison.png", "Yield comparison grouped by type, income vs capital repayment stacked", "Compare section", note="synthetic")
        ctx.close()

        ctx, pg = new(url)
        pg.click("[data-testid=open-alerts]"); pg.wait_for_timeout(150)
        shot(pg, "15-alert-center-empty.png", "[data-testid=alert-modal]")
        rec("15-alert-center-empty.png", "Alert Center modal, empty state: instrument, trigger, threshold, sound, browser-sound switch", "Header > Alerts", note="synthetic")
        pg.check("[data-testid=alert-sound-enable]")
        for kind, val, sound, inst in (("yield_above", "5", "chime", "*"), ("price_below", "50", "beep", "DEMO_INVIT_A"), ("premium_above", "20", "tick", "*")):
            pg.select_option("[data-testid=alert-instrument]", inst); pg.select_option("[data-testid=alert-type]", kind)
            pg.select_option("[data-testid=alert-sound]", sound); pg.fill("[data-testid=alert-value]", val); pg.click("[data-testid=alert-add]")
        pg.wait_for_timeout(150)
        shot(pg, "16-alert-center-active-and-triggered.png", "[data-testid=alert-modal]")
        rec("16-alert-center-active-and-triggered.png", "Alert Center with one TRIGGERED and two ACTIVE alerts, created/triggered timestamps (IST), per-alert sound, Re-arm/Delete", "Add alerts", note="synthetic; thresholds chosen for the demo data")
        pg.click("[data-testid=alert-close]"); pg.wait_for_timeout(100)
        shot(pg, "17-alert-banner-and-badge.png", full=False)
        rec("17-alert-banner-and-badge.png", "Triggered-alert banner on the page and the badge on the Alerts button", "After an alert triggers", note="synthetic")
        ctx.close()

        ctx, pg = new(url)
        shot(pg, "18-news-all.png", "#news")
        rec("18-news-all.png", "News & scrip announcements: All news (each item SYNTHETIC-labelled, with source, IST timestamp, headline, summary, original-source link)", "News section", note="synthetic headlines; links point to a reserved .invalid host")
        for f, nm, title in (("reit", "19-news-filter-reits.png", "News filter: REITs"), ("invit", "20-news-filter-invits-infrastructure.png", "News filter: InvITs & infrastructure"), ("corp", "21-news-filter-corporate-announcements.png", "News filter: Corporate announcements")):
            pg.click(f"[data-testid=news-filter-{f}]"); shot(pg, nm, "#news")
            rec(nm, title, "News section filter buttons", note="synthetic")
        shot(pg, "22-sources-freshness-schedule.png", "#sources")
        rec("22-sources-freshness-schedule.png", "Data sources: access, display-cleared flag, schedule, next attempt, freshness, last attempt/success, observed-through", "Sources section", note="synthetic demo sources only")
        pg.click("[data-testid=theme-toggle]"); pg.wait_for_timeout(200)
        shot(pg, "23-dashboard-full-dark.png")
        rec("23-dashboard-full-dark.png", "Dark theme (whole page)", "Header > Theme", note="synthetic")
        ctx.close()

        ctx, pg = new(servers[1][1])
        shot(pg, "24-nothing-cleared-public-build.png")
        rec("24-nothing-cleared-public-build.png", "Public build when no source is cleared for display: all values withheld, news withheld with an honest explanation", "Build with display_cleared=false", note="synthetic; demonstrates the licence gate")
        ctx.close()
        ctx, pg = new(servers[2][1], expect_error=True)
        shot(pg, "25-error-data-missing.png", full=False)
        rec("25-error-data-missing.png", "Error state with Retry when data.json cannot be loaded", "Serve the site without data.json", note="synthetic site, data file removed")
        ctx.close()
        ctx, pg = new(url, 390, 844)
        shot(pg, "26-mobile-390px-full.png")
        rec("26-mobile-390px-full.png", "Mobile layout (390 px): condensed table columns, stacked header", "Narrow viewport", note="synthetic")
        pg.locator("[data-testid=row]", has_text="InvIT Alpha").click(); pg.wait_for_timeout(250)
        shot(pg, "27-mobile-drawer.png", full=False)
        rec("27-mobile-drawer.png", "Detail drawer on mobile (full width)", "Tap a row on a narrow viewport", note="synthetic")
        ctx.close()
        rec(None, "Push or e-mail alert delivery", "-", ok=False, note="not implemented: needs a server and recipient data; alerts run in the open browser tab only")
        rec(None, "G-Sec benchmark and spread columns", "-", ok=False, note="not implemented: no cleared benchmark source")
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
