# M2 Implementation Report

## Status in one paragraph
Working software: a source registry with recorded permission status, an hourly, rate-limited, retrying acquisition cycle with full audit
logging, freshness tracking, cross-source discrepancy handling, a static dashboard with the requested core features, and end-to-end tests
in a real browser. **It is not deployed, and no real market data is displayed**, because data rights are unconfirmed and a domain cannot be
bought by me. Details below.

## Tests (run locally, 22-Oct-2026)
`python -m pytest tests`: **117 passed** in about 6 s (M1: 82; new: 22 operations/unit tests + 13 browser end-to-end tests).
With the git-ignored workbook fixtures absent (as in CI) the 20 workbook-regression tests skip. Chromium end-to-end tests fail on any
console error, including CSP violations. All data in the end-to-end tests is synthetic (`irie/demo.py`).

## What exists, against your priorities
| # | Priority | Result |
|---|---|---|
| 1 | Verify M1 | 82 M1 tests re-run green before any change; M1 behaviour preserved |
| 2 | Registry, hourly scheduling, provenance, validation, freshness, discrepancies | Done and tested (`sources.py`, `ingest.py`, `freshness.py`, `discrepancy.py`, schema additions, `config/sources.json`, `refresh.yml`) |
| 3 | Zero-cost, permitted sources | **Blocked for external sources**: none can be shown to permit automated retrieval or public redistribution. Implemented the permitted route: an operator-supplied file inbox (`USER_SUPPLIED`). Nothing is fetched from NSE/BSE/AMFI/issuers. Draft permission requests written. |
| 4 | InvIT analytics + dashboard | Done on the M1 engine; income/other/capital split always shown or marked unavailable |
| 5 | REITs and ETFs | Done with M1's instrument-specific calculations (REIT rental income, ETF premium/discount, NAV return, category rules); exercised end-to-end on **synthetic** data only |
| 6 | Dashboard core | Summary cards, type/category filters, search, sortable watchlist (no ranking), yield comparison, history charts, CSV export, configurable browser alerts. Not done: push/email alerts, ETF tracking-based alerts |
| 7 | Deploy to a domain | **Not done; blocked** (below) |
| 8 | End-to-end tests and limitations | Done; see below |

## Non-negotiables check
- Hourly attempts 24/7 with rate limiting and retries: implemented (`run-cycle --loop`, per-source cadence, backoff with jitter); **verified only with a fake clock/fetchers and a 5-second live loop, not over days**. Because no source is fetchable, the real job currently records skips.
- Retrieval vs observation time: stored separately (`retrieved_at` vs observation date), shown in the UI and CSV.
- Primary/secondary cross-checks: discrepancy engine compares sources; needs two real sources to matter.
- Missing never zero; capital never income: enforced in the engine and re-asserted at export and in the browser tests.
- Provenance, validation status, audit history: `source_document`, `import_run/issue`, `retrieval_log`, `discrepancy`; nothing is overwritten.
- Public repo without restricted data: fixtures git-ignored; the only data committed is synthetic; no credentials exist. `inbox/` and `*.sqlite` are ignored.
- No charges, purchases or paid data. No ranking or tax logic.

## Precise blockers
1. **Data rights**: no source is CLEARED or display-cleared (reported NSE, BSE and AMFI terms point against automated collection/redistribution). Until written permission exists, the public build shows only instrument identities, source freshness and "withheld". Action: send/adapt `docs/DATA_PERMISSION_REQUESTS.md`.
2. **Legal review** of licensing, SEBI research/advice position, disclaimers, DPDP (Phase 2 checklist).
3. **Domain and hosting account**: must be registered/created by you.
4. **Operator infrastructure and private inbox** for the hourly job; a public GitHub runner cannot hold private data or durable state.
5. **No real REIT/ETF/InvIT data in the system**: the first real inbox files (or cleared feeds) are needed to exercise the pipeline on real data.

## Known limitations
- Dashboard values for real instruments cannot be reviewed because none are loaded; charts and tables were exercised on synthetic data.
- Alerts are browser-local and only run when the page is open.
- SQLite is the only database exercised; PostgreSQL is untested. The hourly workflow's cache-based persistence is best-effort.
- `discrepancy` tolerances and grade ranking are design choices; ties are never resolved automatically.
- The NAV staleness (270 days), price staleness (3 days) and other thresholds are unchanged configurable defaults.
- Price/NAV history charts need history in the inbox; a single observation yields no chart.
- `_headers` applies on Cloudflare/Netlify-style hosts only; elsewhere the CSP meta tag is the control.

## Modified / new files
Modified: `irie/schema.sql`, `irie/storage.py`, `irie/importing.py` (event id now includes source and grade; leverage and instrument importers), `irie/result.py` (new blocking flag; no-attribution rule), `irie/calc/distributions.py`, `irie/calc/etf.py` (source attribution), `irie/cli.py`, `.gitignore`.
New: `irie/{sources,ingest,freshness,discrepancy,export,site,demo}.py`, `irie/web/*`, `config/sources.json`, `.github/workflows/{ci,refresh}.yml`, `docs/M2_OPERATIONS.md`, `docs/DATA_PERMISSION_REQUESTS.md`, `tests/test_operations.py`, `tests/test_e2e_dashboard.py`, this report.

## Claude usage
Not verifiable from here; please run `/cost`.

## Next concrete action
You: send the permission requests and book the legal review; place real inbox files if you have rights to them. Me, once any of that lands: record clearance in the registry, run a real cycle, review the real dashboard, then deploy per `docs/M2_OPERATIONS.md` section 6.
