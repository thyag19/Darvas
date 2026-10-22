# M2: operations, dashboard and deployment

## 1. Pipeline
`inbox/<SOURCE>/*.csv` -> `irie run-cycle` -> SQLite -> `irie build-site` -> static files (`index.html`, `app.js`, `style.css`, `data.json`, `_headers`).

```
python -m irie.cli run-cycle  --db irie.sqlite [--registry config/sources.json] [--inbox inbox] [--loop --interval 3600] [--force]
python -m irie.cli build-site --db irie.sqlite --out dist --mode public     # public: values only for display-cleared, flag-free figures
python -m irie.cli build-demo --out /tmp/demo                                # SYNTHETIC data only; never real market data
```
Every cycle logs one `retrieval_log` row per registered source, including skipped ones, so staleness is auditable. The cycle is
idempotent (documents are deduplicated by SHA-256; observations are `INSERT OR IGNORE`). Exit code 1 if any source ended in ERROR.

### Hourly, 24/7
`--loop` attempts every `--interval` seconds (default 3600) and each source is attempted when `cadence_s` (default 3600) has elapsed
(with 120 s slack). Per-source rate limiting (`min_interval_s`), up to `max_attempts` tries with exponential backoff and jitter,
permanent errors (403/404/451, hash mismatch) are never retried, and one failing source never stops the others. Run it under an
init system you control, for example (untested here):
```
# /etc/systemd/system/irie.service
[Service] ExecStart=/usr/bin/python3 -m irie.cli run-cycle --loop --db /var/lib/irie/irie.sqlite --inbox /var/lib/irie/inbox
Restart=always
```
or `17 * * * * python -m irie.cli run-cycle ...` from cron. `.github/workflows/refresh.yml` is the same job on GitHub Actions, **inert until
the repository variable `IRIE_REFRESH_ENABLED=true`**; it deploys nothing, keeps state only in a best-effort cache, and GitHub disables
scheduled workflows after 60 idle days.

## 2. Source registry (`config/sources.json`)
`access` is a recorded permission decision: `CLEARED` (needs `clearance_evidence` + `terms_checked_on`), `USER_SUPPLIED` (files you
put in the inbox; you answer for your right to use them), or `NOT_CLEARED` (logged and skipped, never fetched). `display_cleared`
(may values appear on the public site) is separate, defaults to false, and needs `display_evidence`. `irie.sources.validate` enforces this.
**As shipped, nothing is CLEARED and nothing is display-cleared**; NSE, BSE, AMFI and ISSUER are registered as NOT_CLEARED with their
reported terms URLs and have no fetcher.

## 3. Inbox file formats (UTF-8 CSV, ISO dates `yyyy-mm-dd`, blank = unavailable, never zero)
Files are matched by prefix and processed in dependency order. A file that referenced unknown instruments is retried next cycle.
| Prefix | Required columns | Optional |
|---|---|---|
| `instruments_*.csv` | key,name,type | etf_category,distributes(Y/N),isin,nse_symbol,bse_symbol,bse_scrip |
| `distributions_*.csv` | instrument_key,ex_date,total_per_unit | record_date,interest,dividend,rental(REIT),other_income,capital_repayment,include,amount_grade,source_id,period_label,status_text,notes |
| `prices_*.csv` | instrument_key,date,price | venue,source_id |
| `navs_*.csv` | instrument_key,nav_date,nav | kind(FAIR_VALUE/BOOK/FUND_NAV),grade,source_id |
| `leverage_*.csv` | instrument_key,date,value,definition | grade,definition_note,source_id |
Rows naming a source id we do not know are attributed to the file's provider and the original id is kept in `notes`.
Validation and the rejected/ambiguous report are as in M1 (`docs/M1_TECHNICAL.md`, section 5); the per-document totals are in `retrieval_log`.

## 4. Provenance, time and verification
- **Two clocks:** `retrieved_at` (UTC, when we fetched) is stored beside the observation date (`trade_date`, `nav_date`, `ex_date`, IST market date). `retrieval_log.observed_through` is the latest observation date seen. `as_of` is the IST date of the run.
- **Freshness** per source: FRESH / STALE (last good retrieval older than `max_staleness_s`) / NEVER / NOT_FETCHED, plus last attempt, status and consecutive failures.
- **Cross-verification:** observations for the same instrument/date(/venue) from different sources are compared. Agreement within tolerance corroborates (highest grade used, no double counting of distributions). Disagreement keeps both rows, records an OPEN `discrepancy`, flags affected metrics `SOURCE_DISCREPANCY` (blocking), and proceeds only if one source clearly outranks the other (exchange > issuer > regulator > aggregator > unknown); ties yield an amount-unavailable placeholder. Resolved discrepancies are never reopened or deleted.
- Only values with a source attribution, no blocking flag and a display-cleared source are ever published.

## 5. Dashboard (`irie/web`)
Static HTML/JS, no framework, no third-party requests, strict CSP. It renders `data.json` and computes nothing. Summary cards; type, ETF-category and
text filters; "only with a yield shown"; sortable watchlist (user-chosen sort, unavailable values always last; **no ranking or score**); stars persisted in
`localStorage`; yield comparison grouped by instrument type (income / other / capital repayment stacked, grey where the split is unavailable); per-instrument
detail with distribution history per payment, price and NAV history, metrics with status/flags/reasons and sources; CSV export of the filtered view (comment
header with as-of and notice; blank = unavailable or withheld); configurable alerts stored in the browser; sources and freshness table.
Alerts: yield above/below, premium to NAV above/below, capital-repayment share above, price data older than N hours. They fire only on published figures
without blocking flags. Not implemented: push/email notifications (they need a server and recipient data), alerts on ETF tracking metrics.

## 6. Deployment: status and exact blockers
**Not deployed.** Required before a public launch, none of which I can do or assume:
1. **Data rights.** No source is CLEARED or display-cleared. Without them a public build shows identities, freshness and "withheld" only. Draft requests: `docs/DATA_PERMISSION_REQUESTS.md`.
2. **Legal review** (data licensing, SEBI research/advice position, disclaimers, DPDP): checklist in `PHASE2_FEASIBILITY_REPORT.md`, section 6.
3. **A dedicated domain** must be registered by you (no purchases here); then point DNS at your static host.
4. **A hosting account of yours** (any static host; direct upload of `dist/`). Cloudflare Pages / GitHub Pages free-tier limits are in the Phase 2 report; re-check them. `_headers` is Cloudflare/Netlify syntax; on GitHub Pages the CSP `<meta>` still applies but response headers cannot be set.
5. **Operator infrastructure** for the hourly job and a private inbox (a public GitHub runner has no private data store).
Runbook once 1-4 are met: set `display_cleared` + evidence in the registry for the cleared sources only, run a cycle, `build-site --mode public`, inspect `data.json`, upload `dist/`, attach the domain, confirm HTTPS.
