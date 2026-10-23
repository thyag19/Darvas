# M3 Implementation Report

Scope: screenshots of the existing UI, market-hours scheduling, a redesigned complete UI, data-source feasibility, REIT/ETF completion, tests, docs.
Nothing is deployed; no real market data is displayed; no uncleared source is fetched; no restricted data, private fixtures or credentials are committed.

## 1. Screenshots (real Chromium, synthetic demo data only)
- `artifacts/screenshots/before/` - the M2 UI before any change: 17 captured, 4 listed NOT IMPLEMENTED (alert modal, news panel, market status, theme switch). Index: `before/README.md`.
- `artifacts/screenshots/after/` - the redesigned UI: 27 captured, 2 listed NOT IMPLEMENTED (push/e-mail alerts, G-Sec benchmark). Index: `after/README.md`; the tool is `tools/capture_screenshots.py`.
- `artifacts/screenshots/README.md` explains both sets. Every image uses invented demo values and says so.

Current-UI inventory before the work: one scrolling page with cards, filters, a sortable table, inline detail panel, yield bars, an inline alert form (no
timestamps, no sound, no triggered state), a sources table; no news, no market-hours display, no theme, no empty/error design, table clipped on narrow screens.

## 2. Refresh schedule corrected
`irie/market_calendar.py`, `irie/scheduler.py`, `config/market_calendar.json`. Prices: hourly during NSE/BSE sessions only (Asia/Kolkata, 09:15-15:30, weekends,
holidays, exceptional sessions); a year missing from the calendar fails closed. A once-daily off-hours check (default 19:00 IST, validated to be outside the
session, configurable per source) for distributions, announcements, NAV, leverage, holdings. Attempts fetch only the data kinds their window allows. Rate limits,
retries, audit rows, freshness (judged against the schedule) and discrepancy handling are preserved; skips never reset cadence; `--force` never overrides
permission or session rules. **21 fake-clock tests** (full trading day, holiday, weekend, special session and special closure, missing year, daily once per date,
kinds filtering, freshness across a weekend, skip-log dedupe, next-attempt hints, NOT_CLEARED never attempted, shipped config validates).
**Caveat:** the shipped 2026 holiday list is `verified: false` (broker pages that agree with each other, not the exchange circular). Verify it before relying on it.

## 3. Product UI (`irie/web`, `docs/M3_UI.md`)
Original identity (parchment/ink, serif headings, teal/ochre/brick data colours, light and dark). Delivered and browser-tested: header with market-status badge,
summary cards, search/filters/sortable watchlist (no ranking)/starred/CSV, detail drawer with price-and-yield trend, distribution history, component cards
(interest, dividend, rental, other, return of capital - capital labelled as returned capital, not income), ETF NAV/holdings, Compare chart, **News & scrip
announcements** (All / REITs / InvITs & infrastructure / Corporate announcements; source, IST timestamp, headline, summary, original link, SYNTHETIC label,
honest empty states), **Alert Center modal** (7 trigger types, persistence, created/triggered timestamps, ACTIVE/TRIGGERED, re-arm/delete, per-alert sound with a
browser-sound switch, sound once per transition), sources/freshness/schedule table, empty states, error and refresh-failure handling, responsive (no page
overflow at 390 px), keyboard (Enter/Escape), CSP, XSS-safe. News and ETF holdings arrive through new validated inbox kinds (`news_*.csv`, `holdings_*.csv`).
News headlines are third-party content, so they are gated by `display_cleared` exactly like prices. The demo's news is invented and labelled.

## 4. Data sources
`docs/DATA_SOURCES_FEASIBILITY.md`. **Verified as working: only operator-supplied files** (and the synthetic demo). **Still blocked:** NSE, BSE, AMFI (reported terms
require written permission / bar automated collection), index providers, RBI benchmark (terms not established), issuers/AMCs (per-issuer permission unknown),
DhanHQ (paid, redistribution terms not found), Yahoo/aggregators (excluded). SEBI has a stated permission-by-e-mail route that has not been used (needs your
decision). I could read none of the exchange/AMFI pages directly, so their terms are search-reported and must be confirmed. No zero-cost source with
established automated-retrieval *and* public-display rights was found; this is reported as a gap.

## 5. REIT and ETF completion
Reviewed M1 definitions. Added ETF `holdings_top10_weight` (refuses a portfolio not summing to ~100%, flags stale/short lists), REIT/ETF export blocks, and 29
synthetic tests (REIT five-component split, return-of-capital-only, rental-driven income growth, REIT leverage and NAV staleness through the registry, the pinned ETF
category applicability matrix, debt ETF without tracking difference, distributing ETF caveats, and a missing-data sweep over every instrument type/category: never OK,
never zero). No ranking, tax or recommendation logic was added.

## 6. Tests
`python -m pytest tests`: **179 passed** (about 14 s) locally with the git-ignored workbook fixtures present: distributions 21, importing/storage 26, operations 22,
scheduler 21, M3 data 11, REIT/ETF registry 14 + more 18, returns 4, workbook regression 17, browser end-to-end 25. Without the private fixtures (as in CI) the 20
fixture-dependent tests skip. Browser tests fail on any console or CSP error.
Real defects the tests caught and I fixed: a just-triggered alert showed ACTIVE in the open Alert Center; a mobile header overflowed horizontally; a stray "null"
in the detail panel (earlier); the demo's exceptional-session expectation.

## 7. Remaining deployment blockers
1. **Data rights**: nothing is CLEARED or display-cleared; the public build shows identities, freshness and withheld markers only until that changes.
2. **Legal review** (licensing, SEBI research/advice position, disclaimers, DPDP).
3. **Domain and hosting account**: yours to register/create; I did not and cannot.
4. **Operator infrastructure and a private inbox** for the scheduled job (a public GitHub runner holds no private data).
5. **Verify the market calendar** (`verified: false`) against the NSE/BSE circular and add exceptional sessions.
6. No real REIT/InvIT/ETF data is loaded, so the real dashboard is unreviewed; PostgreSQL untested; alerts are browser-tab only; no G-Sec benchmark.

## 8. Claude usage
Not verifiable from inside this session; please run `/cost`.

## 9. Files
New: `irie/{market_calendar,scheduler}.py`, `config/market_calendar.json`, `tests/{test_scheduler,test_m3_data,test_reit_etf_more}.py`, `docs/{DATA_SOURCES_FEASIBILITY,M3_UI}.md`,
`artifacts/screenshots/**`, this report. Rewritten: `irie/web/{index.html,app.js,style.css}`, `tests/test_e2e_dashboard.py`, `tools/capture_screenshots.py`.
Modified: `irie/{ingest,freshness,sources,storage,importing,export,demo,cli,registry,result,models}.py`, `irie/calc/etf.py`, `irie/schema.sql`, `irie/web/_headers`
(unchanged content), `config/sources.json`, `.github/workflows/refresh.yml`, `docs/M2_OPERATIONS.md`, `tests/test_operations.py`.

## M4 follow-up
Defects found by the M4 review (disputed prices charted/alertable, table wider than its box, unreadable phone charts, uninstalled web assets, installed-package calendar lookup) are fixed; the calendar now records per-date verification (nothing verified), a pre-publication gate exists, and the data-source assessment is extended. See `M4_DEPLOYMENT_READINESS_REPORT.md`.
