# Screenshots - before M3 (current UI)

Rendered by real Chromium from the dashboard in this repository, using **synthetic demo data only** (`irie/demo.py`). Every name, price, yield and date is invented; none of it is market data. Regenerate with `python tools/capture_screenshots.py --out <dir>`.

| File | View | How to reach it | Status | Notes |
|---|---|---|---|---|
| `01-dashboard-watchlist-full.png` | Main dashboard: summary cards, filters, watchlist, yield comparison, sources | Open the site root | captured | synthetic demo data |
| `02-summary-cards.png` | Summary cards | Top of the dashboard | captured | synthetic |
| `03-watchlist-table.png` | Sortable watchlist table | Table under Filters; click a column header to sort | captured | synthetic; shows n/a and withheld states |
| `04-watchlist-sorted-yield-desc.png` | Watchlist sorted by headline yield, descending (unavailable values last) | Click the 'Headline TTM yield' header twice | captured | synthetic |
| `05-watchlist-starred-only.png` | Starred-instruments watchlist filter | Star a row, tick 'Watchlist only' | captured | synthetic |
| `06-filters-etf-search.png` | Type filter (ETF) plus text search ('gold') | Choose Type = ETF and type in Search | captured | synthetic |
| `07-empty-state-no-results.png` | Empty state for a search with no results | Search for text that matches nothing | captured | synthetic; the current UI shows only an empty table body, no explanatory empty-state message |
| `08-export-csv-control.png` | CSV export control (filters bar); the downloaded file is saved as export-sample.csv | Click 'Export CSV' | captured | synthetic; a browser download has no page, so the file itself is attached |
| `09-instrument-detail-invit.png` | Instrument detail (InvIT): distribution history with component split, price and NAV history, metrics table | Click any watchlist row | captured | synthetic |
| `10-instrument-detail-reit-discrepancy.png` | Instrument detail (REIT) showing an open cross-source discrepancy and withheld figures | Click the REIT row | captured | synthetic discrepancy created by irie.demo |
| `11-instrument-detail-etf.png` | Instrument detail (ETF): NAV history, premium/discount, NAV return; no income/capital split | Click the ETF row | captured | synthetic |
| `12-yield-comparison.png` | Yield comparison chart grouped by instrument type | Section 'Yield comparison' | captured | synthetic |
| `13-alerts-inline-form-and-triggered.png` | Alerts: inline form, configured triggers and triggered banner (current UI has no modal Alert Center) | Scroll to 'Alerts' and add a rule | captured | synthetic |
| - | Alert Center modal with timestamps and sound selection | - | NOT IMPLEMENTED | current UI: alert form is inline, no per-alert timestamps, no TRIGGERED state, no sound |
| `14-sources-freshness.png` | Data sources and freshness table (access status, display-cleared, freshness, last attempt, observed-through) | Bottom of the page | captured | synthetic demo sources only |
| `15-data-quality-nothing-cleared.png` | Public build when no source is cleared for display: every value withheld | Build with display_cleared=false | captured | synthetic; demonstrates the licence gate |
| `16-mobile-390px-full.png` | Mobile layout (390 px wide) | Narrow viewport | captured | synthetic |
| `17-error-state-data-missing.png` | Error state when data.json cannot be loaded | Serve the site without data.json | captured | synthetic site, data file removed |
| - | Live news feed and scrip announcements panel | - | NOT IMPLEMENTED | no such UI in this build |
| - | Market-hours / refresh-schedule status | - | NOT IMPLEMENTED | no such UI in this build |
| - | Light/dark theme switch | - | NOT IMPLEMENTED | no such UI in this build |
