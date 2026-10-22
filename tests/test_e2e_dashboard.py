"""End-to-end: build the dashboard from SYNTHETIC demo data (through the real ingest cycle), serve it, drive it in Chromium."""
import csv
import datetime as dt
import glob
import io
import json
import threading
import functools
import http.server
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

from irie import demo, export, ingest, site, storage as st  # noqa: E402

CHROME = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0]


def build(tmp, inbox_writer=None, registry=None):
    inbox = tmp / "inbox"
    (inbox_writer or demo.write_demo_inbox)(inbox)
    conn = st.connect(); st.init_schema(conn)
    reg = registry or demo.demo_registry()
    ingest.run_cycle(conn, reg, {k: ingest.FileInboxFetcher(inbox, lambda: demo.DEMO_NOW) for k in reg}, lambda: demo.DEMO_NOW)
    out = tmp / "site"
    site.build_site(export.dumps(export.build_dataset(conn, reg, demo.DEMO_NOW, "public")), out)
    return out


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        except Exception as e:  # pragma: no cover
            pytest.skip(f"chromium unavailable: {e}")
        yield b
        b.close()


def serve(directory):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


@pytest.fixture(scope="module")
def app(tmp_path_factory, browser):
    out = build(tmp_path_factory.mktemp("e2e"))
    srv, url = serve(out)
    yield browser, url
    srv.shutdown()


@pytest.fixture()
def page(app):
    browser, url = app
    ctx = browser.new_context(accept_downloads=True)
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(url)
    pg.wait_for_selector("[data-testid=row]")
    pg.errors = errors
    yield pg
    assert not errors, errors
    ctx.close()


def rows(pg):
    return pg.locator("[data-testid=row]").all_inner_texts()


def cell(pg, name, col):
    r = pg.locator("[data-testid=row]", has_text=name)
    return r.locator("td").nth(col).inner_text()


def test_loads_with_notice_cards_and_all_instruments(page):
    assert "Values are shown only for sources recorded as cleared" in page.inner_text("[data-testid=notice]")
    assert len(rows(page)) == 7
    assert page.locator("[data-testid=card]").count() == 7
    assert "Data as of 2026-10-22" in page.inner_text("[data-testid=meta]")


def test_type_category_and_search_filters(page):
    page.select_option("[data-testid=type-filter]", "ETF")
    assert len(rows(page)) == 3
    page.select_option("[data-testid=cat-filter]", "GOLD_SILVER")
    assert len(rows(page)) == 1 and "Gold" in rows(page)[0]
    page.select_option("[data-testid=cat-filter]", "ALL")
    page.select_option("[data-testid=type-filter]", "ALL")
    page.fill("[data-testid=search]", "beta")
    assert len(rows(page)) == 1 and "Beta" in rows(page)[0]
    page.fill("[data-testid=search]", "zzz-none")
    assert rows(page) == []
    page.fill("[data-testid=search]", "")
    page.check("[data-testid=only-data]")
    assert len(rows(page)) == 3                    # A and B (verified) and the debt ETF; C and the REIT are withheld


def test_sorting_is_user_driven_and_puts_unavailable_last_in_both_directions(page):
    page.click("[data-testid=sort-ttm_yield]")
    asc = [cell(page, n, 3) for n in ("Alpha (synthetic)", "Beta")]
    names = [t.split("\n")[0] for t in rows(page)]
    vals = [r.locator("td").nth(4).inner_text() for r in page.locator("[data-testid=row]").all()]
    shown = [float(v.rstrip("%")) for v in vals if v.endswith("%")]
    assert shown == sorted(shown) and len(shown) >= 2
    assert not any(v.endswith("%") for v in vals[len(shown):])           # n/a and withheld all after the numbers
    page.click("[data-testid=sort-ttm_yield]")
    vals = [r.locator("td").nth(4).inner_text() for r in page.locator("[data-testid=row]").all()]
    shown = [float(v.rstrip("%")) for v in vals if v.endswith("%")]
    assert shown == sorted(shown, reverse=True) and not any(v.endswith("%") for v in vals[len(shown):])
    assert page.locator("th[aria-sort=descending]").count() == 1


def test_unavailable_and_withheld_are_never_shown_as_zero(page):
    assert cell(page, "Beta", 5) == "n/a"                     # no component split disclosed: income yield unavailable
    assert cell(page, "Gamma", 4) == "withheld"               # aggregator-grade amounts: blocking flag
    assert cell(page, "REIT Alpha", 4) == "withheld"          # cross-source price discrepancy
    for t in rows(page):
        assert "0.00%" not in t or "Alpha (synthetic)" in t   # no phantom zero for withheld/unavailable cells


def test_capital_repayment_is_shown_separately_from_income(page):
    r = page.locator("[data-testid=row]", has_text="InvIT Alpha")
    income, share = r.locator("td").nth(5).inner_text(), r.locator("td").nth(6).inner_text()
    head = r.locator("td").nth(4).inner_text()
    assert float(income.rstrip("%")) < float(head.rstrip("%")) and float(share.rstrip("%")) > 10


def test_watchlist_persists_across_reload(page, app):
    r = page.locator("[data-testid=row]", has_text="Beta")
    r.locator("[data-testid=star]").click()
    page.check("[data-testid=only-watch]")
    assert len(rows(page)) == 1
    page.reload()
    page.wait_for_selector("[data-testid=row]")
    page.check("[data-testid=only-watch]")
    assert len(rows(page)) == 1 and "Beta" in rows(page)[0]
    page.evaluate("localStorage.clear()")


def test_yield_chart_groups_by_type_and_excludes_withheld(page):
    assert page.locator("[data-testid=bars-INVIT]").count() == 1
    assert page.locator("[data-testid=bars-REIT]").count() == 0       # REIT yield withheld (discrepancy)
    assert page.locator("[data-testid=bars-INVIT] rect").count() >= 4  # A: 3 stacked segments, B: 1 grey
    txt = page.inner_text("[data-testid=yield-chart]")
    assert "Gamma" not in txt and "capital repayment" in txt


def test_detail_panel_history_and_discrepancy(page):
    page.locator("[data-testid=row]", has_text="REIT Alpha").click()
    assert page.is_visible("[data-testid=detail]")
    assert "Open source discrepancy" in page.inner_text("[data-testid=discrepancy]")
    page.locator("[data-testid=row]", has_text="InvIT Alpha").click()
    assert page.locator("[data-testid=dist-chart] rect").count() >= 8 * 2        # 8 payments, stacked split
    assert "Price history" in page.inner_text("[data-testid=detail]")
    assert "retrieved 2026-10-22T10:00:00Z" in page.inner_text("[data-testid=detail]")
    assert "null" not in page.inner_text("[data-testid=detail]").lower().split()   # no stringified nulls leak into the UI
    csp = page.get_attribute("meta[http-equiv=Content-Security-Policy]", "content")
    assert "default-src 'self'" in csp and "script-src" not in csp.replace("default-src", "")  # scripts only from self


def test_csv_export_matches_filter_and_marks_unavailable_blank(page):
    page.select_option("[data-testid=type-filter]", "INVIT")
    with page.expect_download() as dl:
        page.click("[data-testid=csv]")
    text = Path(dl.value.path()).read_text()
    lines = [l for l in text.splitlines() if not l.startswith("#")]
    assert text.startswith("# as_of 2026-10-22") and "never zero" in text
    recs = list(csv.DictReader(io.StringIO("\n".join(lines))))
    assert [r["key"] for r in recs] == ["DEMO_INVIT_A", "DEMO_INVIT_B", "DEMO_INVIT_C"]
    by = {r["key"]: r for r in recs}
    assert by["DEMO_INVIT_B"]["income_yield"] == "" and by["DEMO_INVIT_B"]["income_yield_status"] == "UNAVAILABLE"
    assert by["DEMO_INVIT_C"]["ttm_yield"] == "" and "withheld" in by["DEMO_INVIT_C"]["ttm_yield_status"]
    assert float(by["DEMO_INVIT_A"]["ttm_yield"]) > 0


def test_alerts_fire_only_on_reliable_figures_and_are_removable(page):
    page.select_option("[data-testid=alert-type]", "yield_above")
    page.fill("[data-testid=alert-value]", "5")
    page.click("[data-testid=alert-add]")
    hits = page.locator("[data-testid=alert-hit]").all_inner_texts()
    assert any("InvIT Alpha" in h for h in hits) and any("InvIT Beta" in h for h in hits)
    assert not any("Gamma" in h or "REIT Alpha" in h for h in hits)          # withheld/flagged figures never alert
    page.reload(); page.wait_for_selector("[data-testid=row]")
    assert page.locator("[data-testid=alert-item]").count() == 1               # persisted
    page.locator("[data-testid=alert-item] button").click()
    assert page.locator("[data-testid=alert-hit]").count() == 0
    page.select_option("[data-testid=alert-type]", "data_stale")
    page.fill("[data-testid=alert-value]", "0.001")
    page.click("[data-testid=alert-add]")
    assert page.locator("[data-testid=alert-hit]").count() >= 7                # retrieval older than the threshold
    page.evaluate("localStorage.clear()")


def test_sources_table_shows_freshness_and_cleared_status(page):
    t = page.inner_text("[data-testid=sources]")
    assert t.count("FRESH") >= 2 and "USER_SUPPLIED" in t and "yes" in t
    assert page.locator("[data-testid=source-row]").count() == 2
    assert "2026-10-22T10:00:00Z" in t and "2026-10-21" in t                   # retrieval time AND observation date


def test_hostile_instrument_name_cannot_execute_script(tmp_path, browser):
    def writer(root):
        demo.write_demo_inbox(root)
        f = Path(root) / "DEMO" / "instruments_demo.csv"
        f.write_text(f.read_text().replace("DEMO InvIT Alpha (synthetic)", '<img src=x onerror="window.__xss=1">'))
    out = build(tmp_path, writer)
    srv, url = serve(out)
    try:
        pg = browser.new_page()
        pg.goto(url); pg.wait_for_selector("[data-testid=row]")
        assert pg.evaluate("window.__xss") is None
        assert "<img src=x" in pg.inner_text("[data-testid=table]")            # shown as text
        pg.close()
    finally:
        srv.shutdown()


def test_public_build_with_nothing_cleared_shows_no_values(tmp_path, browser):
    import dataclasses
    reg = {k: dataclasses.replace(v, display_cleared=False, display_evidence="") for k, v in demo.demo_registry().items()}
    out = build(tmp_path, registry=reg)
    srv, url = serve(out)
    try:
        pg = browser.new_page()
        pg.goto(url); pg.wait_for_selector("[data-testid=row]")
        body = pg.inner_text("[data-testid=table]")
        assert "%" not in body and "withheld" in body
        assert pg.locator("[data-testid=no-yield]").count() == 1
        pg.close()
    finally:
        srv.shutdown()
