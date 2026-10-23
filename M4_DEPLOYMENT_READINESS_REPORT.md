# M4 Deployment Readiness & Final Validation Report

Starting point `ab08fe1`. Nothing was deployed, no domain bought, no account created, no uncleared source fetched, no restricted data committed.
**This is a validated, deployable static application with no permitted live data feed. It is not launch-ready for genuine live data.**

## 1. Tests and defects fixed
`python -m pytest tests`: **231 passed** (~15 s), up from 179. By file: e2e browser 34, M4 validation 35, importing/storage 26, scheduler 21, distributions 21, operations 22, REIT/ETF registry 14 + more 18,
workbook regression 17 (needs the private, git-ignored fixtures; skips in CI), M3 data 12, calendar verification 7, returns 4. Browser tests fail on any console/CSP error.
`tools/verify_clean_install.sh` (fresh virtualenv, `pip install .`, run from outside the source tree, repeatable build, gate) passes.

Defects demonstrated and fixed (each with a regression test):
| Defect | Evidence | Fix |
|---|---|---|
| A price two sources disagree on was still shown, charted and could trigger a price alert | REIT drawer chart and `price_above` alert | `latest.price` withheld as "disputed"; disputed dates removed from price/NAV history and yield trend; alerts suppressed |
| Watchlist table 1586 px wide in a 1240 px box (scrolled sideways on a laptop) | element screenshot width | columns wrap, secondary columns hidden below 1180 px; tested at 1440/1280/1100 and page-overflow at 960/768/600 |
| Chart text unreadably small on phones | scale 0.6 | chart width follows the screen; tested scale >= 0.9 |
| Installed package lacked the dashboard files | `pip install .` check | `web/*` added to package data |
| Installed demo build looked for the calendar next to site-packages | clean-install run | calendar lookup falls back safely; real scheduling refuses to run without one (exit 2) |
| Screenshot tool captured the sticky header mid-page | dark full-page shot | instant scroll before capture |
| (also) smooth scrolling ignored reduced-motion preference | review | respects `prefers-reduced-motion` |
M4 verified without needing a fix: REIT components (interest, dividend, rental, other, return of capital) reconcile per payment and capital never enters income; ETF category matrix and holdings validation; stale, conflicting and withheld data never reach the public build; alert persistence, TRIGGERED transition, timestamps, sound switch, once-only sound, invalid-data suppression; exports carry only OK, attributed, non-withheld values; the synthetic demo contains no ISIN-shaped identifier, no real name from a denylist, no real exchange label (demo venue is `DEMO-EXCH`); no restricted file, fixture, database or secret pattern is tracked.

## 2. Screenshots
`artifacts/screenshots/after/` (27 views, regenerated after the fixes) and **contact sheet `artifacts/screenshots/after/contact-sheet.png`**; index `artifacts/screenshots/after/README.md`. `before/` is the pre-M3 UI. All synthetic.
Reviewed: dashboard, drawers (InvIT, REIT, ETF, split-unavailable), Alert Center (empty, active/triggered), news filters, themes, mobile, error and nothing-cleared states, CSV export (sample file and tests).

## 3. Market calendar: verification status
**Not verified.** I identified the official circulars and could not read them: `nsearchives.nseindia.com` is blocked by this environment's network policy (HTTP 403 on CONNECT; fetch tool cannot resolve it).
| Item | Status | Evidence |
|---|---|---|
| 2026 trading holidays (16 dates) | `unverified_secondary` (0 verified) | broker/fund-house pages that agree; official circular NSE/CMTR/71775 (12-Dec-2025) identified, content not read; its weekend rows and the F&O circular NSE/FAOP/71777's 15 weekday closures were quoted in search snippets |
| 15-Jan-2026 | `disputed` | some sources say trading holiday; an official NSE Clearing circular found only changes the settlement schedule. Past date; treated as closed |
| Regular session 09:15-15:30 IST | `unverified_secondary` | widely reported; not read from a circular |
| Muhurat Sunday 8-Nov-2026 | **pending, not polled** | press: main session 14:20-15:30, pre-open 14:05-14:20, minute-level differences between reports; circular NSE/CMTR/76941 (19-Oct-2026) identified, not read. Fail closed. |
| 2027 and later | not loaded | market polling fails closed |
Code: per-date status; a date cannot be `verified_official` without `evidence_url`, `checked_on` and an official circular with `read: true`; a calendar is `verified` only if every fact is verified, `holidays_complete` is asserted, and no exceptional session is pending; exceptional sessions are only honoured when verified, otherwise listed as pending and not polled. The dashboard badge says "calendar unverified" and its tooltip shows "0 of 16 holiday dates verified". Fake-clock tests: 28 (open/close edges, weekend, holiday, special session and closure, pending session, missing year, IST/UTC year boundary, daily check once per date).
**To finish:** allow `nsearchives.nseindia.com` in the environment's network settings (single-document reads), or paste the circular text, then set the statuses with evidence.

## 4. Data sources assessed (`docs/DATA_SOURCES_FEASIBILITY.md`, incl. M4 addendum)
Issuer websites (IndiGrid disclaimer: viewing/reference only, no copying or distributing; offer documents bar copying), six AMC sites (personal viewing tolerated; aggregation, redistribution or commercial reuse needs written consent), SEBI website policy
(reproduction after permission by e-mail), GODL-India (genuinely open, commercial use with attribution, but no relevant REIT/InvIT/ETF dataset found), NSE free downloads (no statement permitting reuse), exchange filings, plus the Phase 2/M3 set (NSE, BSE, AMFI, RBI, DhanHQ, Yahoo, aggregators, index providers). Each row records fields, access, frequency, restrictions, permission for storage/derived/display/CSV, fees and evidence.
**Result:** no source established that permits automated retrieval, storage, derived metrics, public display and CSV export at zero fee. Free permission routes: SEBI e-mail request; per-issuer and per-AMC written consent. Fallback retained: operator-supplied files, display gate closed by default. I read none of the terms pages in full (all [S]/[T]).

## 5. Implemented versus awaiting real data
| Implemented and tested (on synthetic data) | Needs a permitted live feed to be real |
|---|---|
| Dashboard, sortable watchlist (no ranking), filters, search, CSV; instrument drawers with price/yield/distribution charts and component cards; REIT/InvIT/ETF calculations incl. rental, return of capital, premium/discount, NAV return, holdings; Alert Center with persistence, timestamps, sound; news panel with filters; sources/freshness/schedule table; market-hours scheduler with fail-closed calendar; discrepancy handling; light/dark/responsive; pre-publication gate | Prices, distributions and components, NAV, leverage, holdings, announcements for any real instrument; live news; G-Sec benchmark; ETF tracking error (index licensing); push/e-mail alerts (need a server) |

## 6. Deployment procedure and operations
`docs/DEPLOYMENT.md`: preconditions, build + `check-site` gate, upload steps for a dedicated domain (Cloudflare Pages direct upload recommended; GitHub Pages caveats), HTTPS/headers checks, rollback, and the zero-cost scheduled worker design
(private "ops" repository, cron ticks 03:50-09:50 UTC weekdays + 13:35 UTC daily = ~8 runs/day, inside the free allowance of 2,000 private-repo minutes by my estimate; public repositories' standard runners are free; 60-day inactivity and delay caveats; cache is best-effort, inbox is the source of truth).
`.github/workflows/refresh.yml` is inert until a repository variable is set, has no secrets and no publish step.
Free-tier facts checked by search only (no accounts): GitHub Actions billing, GitHub Pages limits (1 GB, 100 GB/month soft, commercial-use wording), Cloudflare Pages limits (Phase 2/M3), UptimeRobot free tier.

## 7. Exact blockers to a genuine live-data launch
1. **No permitted data source** (written permission for retrieval, storage, derived metrics, display and CSV from at least one source per data category, or a GODL-licensed dataset).
2. **Market calendar unverified**: official circulars unreadable here; Muhurat session unresolved.
3. **Legal review** (licensing, SEBI research/advice position, disclaimers, DPDP).
4. **Your accounts**: domain, host, and a private repository/machine for the worker and inbox; a deploy credential held as a secret there.
5. Real data has never passed through the system, so the real dashboard is unreviewed; PostgreSQL untested; alerts run only in an open browser tab.

## 8. Modified-file inventory
New: `irie/sitecheck.py`, `docs/DEPLOYMENT.md`, `tests/{test_calendar_verification,test_m4_validation}.py`, `tools/{contact_sheet.py,verify_clean_install.sh}`, `artifacts/screenshots/after/contact-sheet.png`, this report.
Modified: `irie/{market_calendar,export,cli,demo}.py`, `irie/web/{app.js,style.css}`, `config/market_calendar.json`, `pyproject.toml`, `.github/workflows/refresh.yml`, `docs/DATA_SOURCES_FEASIBILITY.md`,
`tests/{test_e2e_dashboard,test_m3_data,test_scheduler}.py`, `tools/capture_screenshots.py`, `M3_IMPLEMENTATION_REPORT.md`, `.gitignore`, `artifacts/screenshots/**`. Commit hash: see the final message and `git log` (a report cannot contain its own hash).

## 9. Claude usage
Not verifiable from inside this session (`/cost` is not available to me). Please run it; I will not estimate a figure.
