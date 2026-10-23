"""End-to-end: build the dashboard from SYNTHETIC demo data (through the real ingest cycle), serve it, drive it in Chromium.
Every test fails on any console error, including Content-Security-Policy violations."""
import csv
import dataclasses
import functools
import glob
import http.server
import io
import json
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

from irie import demo, export, ingest, site, storage as st  # noqa: E402
from irie.market_calendar import load_calendar  # noqa: E402

CAL = load_calendar(Path(__file__).resolve().parent.parent / "config" / "market_calendar.json")
CHROME = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome") or [None])[0]


def build(tmp, inbox_writer=None, registry=None, drop_data=False):
    inbox = tmp / "inbox"
    (inbox_writer or demo.write_demo_inbox)(inbox)
    conn = st.connect(); st.init_schema(conn)
    reg = registry or demo.demo_registry()
    ingest.run_cycle(conn, reg, {k: ingest.FileInboxFetcher(inbox, lambda: demo.DEMO_NOW) for k in reg}, lambda: demo.DEMO_NOW, calendar=CAL)
    out = tmp / "site"
    site.build_site(export.dumps(export.build_dataset(conn, reg, demo.DEMO_NOW, "public", CAL)), out)
    if drop_data:
        (out / "data.json").unlink()
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


def open_page(browser, url, w=1360, h=900, expect="[data-testid=row]"):
    ctx = browser.new_context(accept_downloads=True, viewport={"width": w, "height": h})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(url)
    pg.wait_for_selector(expect)
    pg.errors, pg.ctx = errors, ctx
    return pg


@pytest.fixture()
def page(app):
    browser, url = app
    pg = open_page(browser, url)
    yield pg
    assert not pg.errors, pg.errors
    pg.ctx.close()


def rows(pg):
    return pg.locator("[data-testid=row]").all_inner_texts()


def cell(pg, name, col):
    return pg.locator("[data-testid=row]", has_text=name).locator("td").nth(col).inner_text()


def add_alert(pg, kind, value, inst="*", sound="chime"):
    pg.click("[data-testid=open-alerts]")
    pg.select_option("[data-testid=alert-instrument]", inst)
    pg.select_option("[data-testid=alert-type]", kind)
    pg.select_option("[data-testid=alert-sound]", sound)
    pg.fill("[data-testid=alert-value]", str(value))
    pg.click("[data-testid=alert-add]")


# ---- page, header, cards ------------------------------------------------------------------------------------------
def test_loads_with_labelled_synthetic_notice_market_badge_and_cards(page):
    assert "SYNTHETIC DEMO DATA" in page.inner_text("[data-testid=notice]")
    assert len(rows(page)) == 7 and page.locator("[data-testid=card]").count() == 6
    assert "Market data as of 2026-10-22" in page.inner_text("[data-testid=meta]")
    badge = page.inner_text("[data-testid=hours-badge]")
    assert "NSE/BSE open" in badge and "calendar unverified" in badge                  # honest about the unverified holiday list
    assert page.title().startswith("Yield Atlas")


def test_theme_toggle_persists(page, app):
    first = page.evaluate("document.documentElement.getAttribute('data-theme')")
    page.click("[data-testid=theme-toggle]")
    now = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert now in ("light", "dark") and now != first
    page.reload(); page.wait_for_selector("[data-testid=row]")
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == now
    page.evaluate("localStorage.clear()")


# ---- watchlist --------------------------------------------------------------------------------------------------------
def test_type_category_and_search_filters_and_empty_state(page):
    page.select_option("[data-testid=type-filter]", "ETF")
    assert len(rows(page)) == 3
    page.select_option("[data-testid=cat-filter]", "GOLD_SILVER")
    assert len(rows(page)) == 1 and "Gold" in rows(page)[0]
    page.select_option("[data-testid=cat-filter]", "ALL"); page.select_option("[data-testid=type-filter]", "ALL")
    page.fill("[data-testid=search]", "beta")
    assert len(rows(page)) == 1 and "Beta" in rows(page)[0]
    page.fill("[data-testid=search]", "zzz-none")
    assert rows(page) == [] and page.is_visible("[data-testid=empty-state]")
    assert "No instruments match" in page.inner_text("[data-testid=empty-state]")
    page.click("[data-testid=clear-filters]")
    assert len(rows(page)) == 7 and not page.is_visible("[data-testid=empty-state]")
    page.check("[data-testid=only-data]")
    assert len(rows(page)) == 3                      # InvIT A and B (verified) and the debt ETF; C and the REIT are withheld


def test_sorting_is_user_driven_and_puts_unavailable_last_in_both_directions(page):
    for _ in range(2):
        page.click("[data-testid=sort-ttm_yield]")
        vals = [r.locator("td").nth(4).inner_text() for r in page.locator("[data-testid=row]").all()]
        shown = [float(v.rstrip("%")) for v in vals if v.endswith("%")]
        assert len(shown) >= 2 and not any(v.endswith("%") for v in vals[len(shown):])
        want = sorted(shown, reverse=page.locator("th[aria-sort=descending]").count() == 1)
        assert shown == want
    assert page.locator("th[aria-sort=descending]").count() == 1


def test_unavailable_and_withheld_are_never_shown_as_zero(page):
    assert cell(page, "Beta", 5) == "n/a"                  # no component split disclosed: income yield unavailable
    assert cell(page, "Gamma", 4) == "withheld"            # aggregator-grade amounts: blocking flag
    assert cell(page, "REIT Alpha", 4) == "withheld"       # cross-source price discrepancy


def test_capital_repayment_is_shown_separately_from_income(page):
    r = page.locator("[data-testid=row]", has_text="InvIT Alpha")
    head, income, share = (r.locator("td").nth(i).inner_text() for i in (4, 5, 6))
    assert float(income.rstrip("%")) < float(head.rstrip("%")) and float(share.rstrip("%")) > 10


def test_starred_instruments_persist_across_reload(page):
    page.locator("[data-testid=row]", has_text="Beta").locator("[data-testid=star]").click()
    page.check("[data-testid=only-watch]")
    assert len(rows(page)) == 1
    page.reload(); page.wait_for_selector("[data-testid=row]")
    page.check("[data-testid=only-watch]")
    assert len(rows(page)) == 1 and "Beta" in rows(page)[0]
    page.evaluate("localStorage.clear()")


def test_csv_export_matches_filter_and_marks_unavailable_blank(page):
    page.select_option("[data-testid=type-filter]", "INVIT")
    with page.expect_download() as dl:
        page.click("[data-testid=csv]")
    text = Path(dl.value.path()).read_text()
    assert text.startswith("# as_of 2026-10-22") and "never zero" in text
    recs = list(csv.DictReader(io.StringIO("\n".join(l for l in text.splitlines() if not l.startswith("#")))))
    assert [r["key"] for r in recs] == ["DEMO_INVIT_A", "DEMO_INVIT_B", "DEMO_INVIT_C"]
    by = {r["key"]: r for r in recs}
    assert by["DEMO_INVIT_B"]["income_yield"] == "" and by["DEMO_INVIT_B"]["income_yield_status"] == "UNAVAILABLE"
    assert by["DEMO_INVIT_C"]["ttm_yield"] == "" and "withheld" in by["DEMO_INVIT_C"]["ttm_yield_status"]
    assert float(by["DEMO_INVIT_A"]["ttm_yield"]) > 0


# ---- compare + detail drawer -------------------------------------------------------------------------------------------
def test_yield_chart_groups_by_type_and_excludes_withheld(page):
    assert page.locator("[data-testid=bars-INVIT]").count() == 1 and page.locator("[data-testid=bars-REIT]").count() == 0
    assert page.locator("[data-testid=bars-INVIT] rect").count() >= 4
    txt = page.inner_text("[data-testid=yield-chart]")
    assert "Gamma" not in txt and "returned capital, not income" in txt


def test_drawer_invit_shows_history_trend_and_component_cards(page):
    page.locator("[data-testid=row]", has_text="InvIT Alpha").click()
    d = page.locator("[data-testid=drawer]")
    assert d.is_visible() and "InvIT Alpha" in d.inner_text()
    assert page.locator("[data-testid=dist-chart] rect").count() >= 8 * 2          # 8 payments, stacked split
    assert page.locator("[data-testid=trend-chart] polyline").count() == 2         # price and headline-yield lines
    assert page.is_visible("[data-testid=comp-interest]") and page.is_visible("[data-testid=comp-capital_repayment]")
    assert "Returned capital, not income" in page.inner_text("[data-testid=comp-capital_repayment]")
    assert page.locator("[data-testid=comp-rental]").count() == 0                   # rental income is a REIT-only component
    assert "retrieved" in d.inner_text() and "Metrics, status and flags" in d.inner_text()
    page.click("[data-testid=drawer-close]")
    assert not d.is_visible()


def test_drawer_reit_has_rental_component_and_discrepancy(page):
    page.locator("[data-testid=row]", has_text="REIT Alpha").click()
    assert page.is_visible("[data-testid=comp-rental]") and "Open source discrepancy" in page.inner_text("[data-testid=discrepancy]")
    assert "Related announcements" in page.inner_text("[data-testid=drawer]")        # synthetic REIT headline linked by instrument
    page.keyboard.press("Escape")
    assert not page.locator("[data-testid=drawer]").is_visible()


def test_drawer_beta_explains_missing_split_and_etf_shows_holdings(page):
    page.locator("[data-testid=row]", has_text="InvIT Beta").click()
    assert "Not available" in page.inner_text("[data-testid=breakdown-na]") and "No split is estimated" in page.inner_text("[data-testid=breakdown-na]")
    page.keyboard.press("Escape")
    page.locator("[data-testid=row]", has_text="Equity Index ETF").click()
    assert page.locator("[data-testid=holdings] tr").count() == 10 and "Top holdings" in page.inner_text("[data-testid=drawer]")
    assert page.locator("[data-testid=breakdown]").count() == 0                       # an ETF never gets an income/capital split
    page.keyboard.press("Escape")
    page.locator("[data-testid=row]", has_text="Debt ETF").click()
    assert "withheld" in page.inner_text("[data-testid=drawer]")                      # stale holdings figure is blocked


def test_keyboard_opens_drawer(page):
    page.locator("[data-testid=row]", has_text="Gold ETF").focus()
    page.keyboard.press("Enter")
    assert "Gold ETF" in page.inner_text("[data-testid=drawer]")


# ---- news ---------------------------------------------------------------------------------------------------------------
def test_news_panel_filters_labels_and_safe_links(page):
    items = lambda: page.locator("[data-testid=news-item]")
    assert items().count() == 7
    page.click("[data-testid=news-filter-reit]")
    assert items().count() == 2 and all("REIT" in t for t in items().all_inner_texts())
    page.click("[data-testid=news-filter-invit]")
    assert items().count() == 3                                                       # InvIT + infrastructure
    page.click("[data-testid=news-filter-corp]")
    assert items().count() == 2 and all("Corporate announcement" in t for t in items().all_inner_texts())
    page.click("[data-testid=news-filter-all]")
    first = items().first
    text = first.inner_text()
    for needle in ("SYNTHETIC", "Synthetic wire", "published", "IST", "Open original"):
        assert needle in text
    link = first.locator("a")
    assert link.get_attribute("rel") == "noopener noreferrer" and link.get_attribute("target") == "_blank"
    assert link.get_attribute("href").startswith("https://example.invalid/")
    assert page.locator("[data-testid=news-filter-all]").get_attribute("aria-pressed") == "true"


# ---- alert center ---------------------------------------------------------------------------------------------------------
def test_alert_center_modal_empty_state_and_creation_with_timestamps(page):
    page.click("[data-testid=open-alerts]")
    assert page.is_visible("[data-testid=alert-modal]") and page.is_visible("[data-testid=alert-empty]")
    page.select_option("[data-testid=alert-type]", "yield_above"); page.fill("[data-testid=alert-value]", "99")
    page.click("[data-testid=alert-add]")
    item = page.locator("[data-testid=alert-item]")
    assert item.count() == 1 and page.inner_text("[data-testid=alert-state]") == "ACTIVE"
    assert "Created" in item.inner_text() and "IST" in item.inner_text() and "sound: chime" in item.inner_text()
    assert page.locator("[data-testid=alert-hit]").count() == 0                       # a 99% threshold never fires
    page.reload(); page.wait_for_selector("[data-testid=row]")
    page.click("[data-testid=open-alerts]")
    assert page.locator("[data-testid=alert-item]").count() == 1                      # persisted
    page.click("[data-testid=alert-delete]")
    assert page.is_visible("[data-testid=alert-empty]")
    page.evaluate("localStorage.clear()")


def test_alerts_fire_only_on_reliable_figures_persist_and_can_be_rearmed(page):
    add_alert(page, "yield_above", 5, sound="none")
    hits = page.locator("[data-testid=alert-hit]").all_inner_texts()
    assert len(hits) == 1 and "InvIT Alpha" in hits[0] and "triggered" in hits[0] and "IST" in hits[0]
    assert not any("Gamma" in h or "REIT Alpha" in h for h in hits)                  # withheld/flagged figures never alert
    assert page.inner_text("[data-testid=alert-state]") == "TRIGGERED" and page.inner_text("[data-testid=alert-badge]") == "1"
    page.reload(); page.wait_for_selector("[data-testid=row]")
    assert page.locator("[data-testid=alert-hit]").count() == 1                       # triggered state persisted
    page.click("[data-testid=open-alerts]")
    page.click("[data-testid=alert-rearm]")
    assert page.locator("[data-testid=alert-hit]").count() == 1                       # still true, so it fires again immediately
    page.click("[data-testid=alert-delete]")
    assert page.locator("[data-testid=alert-hit]").count() == 0
    page.evaluate("localStorage.clear()")


def test_price_and_staleness_alerts(page):
    add_alert(page, "price_above", 100, inst="DEMO_INVIT_A", sound="none")
    assert "Last price above" in page.locator("[data-testid=alert-hit]").first.inner_text()
    page.select_option("[data-testid=alert-type]", "price_below"); page.select_option("[data-testid=alert-instrument]", "DEMO_INVIT_A")
    page.fill("[data-testid=alert-value]", "50"); page.click("[data-testid=alert-add]")
    assert page.locator("[data-testid=alert-hit]").count() == 1                       # 102 is not below 50
    page.select_option("[data-testid=alert-type]", "data_stale"); page.select_option("[data-testid=alert-instrument]", "*")
    page.fill("[data-testid=alert-value]", "0.001"); page.click("[data-testid=alert-add]")
    assert any("h old" in t for t in page.locator("[data-testid=alert-hit]").all_inner_texts())
    page.evaluate("localStorage.clear()")


def test_alert_sound_obeys_the_browser_switch_and_plays_once(page):
    add_alert(page, "yield_above", 5, sound="chime")                                  # sound switch is off by default
    assert page.evaluate("window.__irieSounds.length") == 0
    page.evaluate("localStorage.clear()"); page.reload(); page.wait_for_selector("[data-testid=row]")
    page.click("[data-testid=open-alerts]")
    page.check("[data-testid=alert-sound-enable]")
    assert page.evaluate("window.__irieSounds.map(s => s.kind)") == ["chime"]         # confirmation chime on enabling
    page.select_option("[data-testid=alert-sound]", "beep"); page.fill("[data-testid=alert-value]", "5")
    page.click("[data-testid=alert-add]")
    assert page.evaluate("window.__irieSounds.map(s => s.kind)") == ["chime", "beep"]
    page.reload(); page.wait_for_selector("[data-testid=row]")
    assert page.evaluate("window.__irieSounds.length") == 0                           # an already-triggered alert is silent after reload
    page.evaluate("localStorage.clear()")


def test_sound_none_is_silent_even_when_enabled(page):
    page.click("[data-testid=open-alerts]"); page.check("[data-testid=alert-sound-enable]")
    page.evaluate("window.__irieSounds.length = 0")
    page.select_option("[data-testid=alert-sound]", "none"); page.fill("[data-testid=alert-value]", "5"); page.click("[data-testid=alert-add]")
    assert page.locator("[data-testid=alert-hit]").count() == 1 and page.evaluate("window.__irieSounds.length") == 0
    page.evaluate("localStorage.clear()")


# ---- sources, errors, responsive, security ----------------------------------------------------------------------------
def test_sources_table_shows_schedule_freshness_and_cleared_status(page):
    t = page.inner_text("[data-testid=sources]")
    assert t.count("fresh") >= 2 and "user supplied" in t and "Local files, hourly" in t and "SYNTHETIC" in t
    assert page.locator("[data-testid=source-row]").count() == 2
    assert "22 Oct 2026, 15:30 IST" in t and "2026-10-21" in t                          # retrieval time AND observation date


def test_refresh_failure_keeps_data_and_warns(page):
    page.route("**/data.json", lambda route: route.fulfill(status=500, body="boom"))
    page.evaluate("window.irieRefresh()")
    page.wait_for_selector("[data-testid=warn]:not([hidden])")
    assert "Could not refresh" in page.inner_text("[data-testid=warn]") and len(rows(page)) == 7
    page.unroute("**/data.json")
    page.evaluate("window.irieRefresh()")
    page.wait_for_function("document.querySelector('[data-testid=warn]').hidden")
    page.errors.clear()                                                                # the deliberate 500 logs a network error


def test_mobile_layout_has_no_horizontal_page_overflow(app):
    browser, url = app
    pg = open_page(browser, url, 390, 844)
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert pg.is_visible("[data-testid=open-alerts]") and pg.locator("[data-testid=row]").count() == 7
    pg.locator("[data-testid=row]", has_text="InvIT Alpha").click()
    assert pg.evaluate("document.querySelector('[data-testid=drawer]').getBoundingClientRect().width <= window.innerWidth")
    assert not pg.errors, pg.errors
    pg.ctx.close()


def test_missing_data_file_shows_an_error_state_with_retry(tmp_path, browser):
    out = build(tmp_path, drop_data=True)
    srv, url = serve(out)
    try:
        ctx = browser.new_context(); pg = ctx.new_page()
        pg.goto(url); pg.wait_for_selector("[data-testid=load-error]")
        assert "Data could not be loaded" in pg.inner_text("[data-testid=load-error]") and pg.is_visible("text=Retry")
        ctx.close()
    finally:
        srv.shutdown()


def test_hostile_text_cannot_execute_script_or_inject_links(tmp_path, browser):
    def writer(root):
        demo.write_demo_inbox(root)
        f = Path(root) / "DEMO" / "instruments_demo.csv"
        f.write_text(f.read_text().replace("DEMO InvIT Alpha (synthetic)", '<img src=x onerror="window.__xss=1">'))
        n = Path(root) / "DEMO" / "news_demo.csv"
        n.write_text(n.read_text() + '2026-10-22T09:00:00Z,x,Other,,"<script>window.__xss=2</script>","<b>bold</b>",javascript:window.__xss=3\n')
    out = build(tmp_path, writer)
    srv, url = serve(out)
    try:
        pg = open_page(browser, url)
        assert pg.evaluate("window.__xss") is None
        assert "<img src=x" in pg.inner_text("[data-testid=table]")
        assert pg.locator("[data-testid=news-item]").count() == 7                       # the javascript: row was rejected at import
        assert pg.locator("#newslist a[href^='javascript']").count() == 0
        pg.ctx.close()
    finally:
        srv.shutdown()


def test_public_build_with_nothing_cleared_shows_no_values_and_honest_news_state(tmp_path, browser):
    reg = {k: dataclasses.replace(v, display_cleared=False, display_evidence="") for k, v in demo.demo_registry().items()}
    srv, url = serve(build(tmp_path, registry=reg))
    try:
        pg = open_page(browser, url)
        body = pg.inner_text("[data-testid=table]")
        assert "%" not in body and "withheld" in body and pg.locator("[data-testid=no-yield]").count() == 1
        assert pg.locator("[data-testid=news-item]").count() == 0
        assert "7 item(s) exist but their source is not cleared" in pg.inner_text("[data-testid=news-empty]")
        pg.locator("[data-testid=row]", has_text="InvIT Alpha").click()
        assert "Not available" in pg.inner_text("[data-testid=breakdown-na]")           # breakdown withheld along with the figures
        assert not pg.errors, pg.errors
        pg.ctx.close()
    finally:
        srv.shutdown()


@pytest.mark.parametrize("width", [1440, 1280, 1100])
def test_watchlist_fits_without_horizontal_scroll_on_laptops(app, width):
    browser, url = app
    pg = open_page(browser, url, width, 900)
    sw, cw = pg.evaluate("(() => { const t = document.querySelector('.tablewrap'); return [t.scrollWidth, t.clientWidth]; })()")
    assert sw <= cw + 1, (width, sw, cw)
    assert not pg.errors, pg.errors
    pg.ctx.close()


def test_disputed_price_is_not_shown_charted_or_alertable(page):
    assert cell(page, "REIT Alpha", 3) == "disputed"                                  # two sources disagree on the latest close
    page.locator("[data-testid=row]", has_text="REIT Alpha").click()
    assert "disputed" in page.inner_text("[data-testid=drawer]").lower() or "withheld" in page.inner_text("[data-testid=drawer]")
    page.keyboard.press("Escape")
    add_alert(page, "price_above", 1, inst="DEMO_REIT_A", sound="none")               # 316 > 1 would fire on an undisputed price
    assert page.locator("[data-testid=alert-hit]").count() == 0
    assert page.inner_text("[data-testid=alert-state]") == "ACTIVE"
    page.evaluate("localStorage.clear()")


def test_chart_text_stays_readable_on_a_phone(app):
    browser, url = app
    pg = open_page(browser, url, 390, 844)
    pg.locator("[data-testid=row]", has_text="InvIT Alpha").click()
    scale = pg.evaluate("(() => { const s = document.querySelector('[data-testid=trend-chart]'); return s.getBoundingClientRect().width / s.viewBox.baseVal.width; })()")
    assert scale >= 0.9, scale                                                          # 11px SVG text renders at >= ~10px
    assert not pg.errors, pg.errors
    pg.ctx.close()


@pytest.mark.parametrize("width", [960, 768, 600])
def test_tablet_widths_scroll_the_table_inside_its_box_never_the_page(app, width):
    browser, url = app
    pg = open_page(browser, url, width, 900)
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    assert not pg.errors, pg.errors
    pg.ctx.close()


def test_csv_export_carries_only_published_correctly_attributed_values(page):
    with page.expect_download() as dl:
        page.click("[data-testid=csv]")
    text = Path(dl.value.path()).read_text()
    recs = list(csv.DictReader(io.StringIO("\n".join(l for l in text.splitlines() if not l.startswith("#")))))
    assert len(recs) == 7
    metrics = sorted({k[:-len("_status")] for k in recs[0] if k.endswith("_status")})
    for r in recs:
        if r["price"]:                                                              # every shown price names its source, date and retrieval time
            assert r["price_source"] == "DEMO" and r["price_date"] and r["price_retrieved_at"].endswith("Z")
        for m in metrics:
            if r[m] != "":
                assert r[m + "_status"] == "OK", (r["key"], m)                      # a value only ever accompanies an OK, non-withheld status
                assert "UNVERIFIED_SOURCE" not in r[m + "_flags"] and "SOURCE_DISCREPANCY" not in r[m + "_flags"]
    by = {r["key"]: r for r in recs}
    assert by["DEMO_REIT_A"]["price"] == "" and by["DEMO_INVIT_C"]["ttm_yield"] == ""   # disputed price / aggregator-grade amounts are blank
    assert by["DEMO_ETF_GOLD"]["ttm_dpu_status"] == "NOT_APPLICABLE" and by["DEMO_ETF_GOLD"]["ttm_dpu"] == ""
