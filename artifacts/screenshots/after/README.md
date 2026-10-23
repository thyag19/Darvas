# Screenshots - after M4 (validated UI)

Rendered by real Chromium from the dashboard in this repository, using **synthetic demo data only** (`irie/demo.py`). Every name, price, yield and date is invented; none of it is market data. Regenerate with `python tools/capture_screenshots.py --out <dir>`.

| File | View | How to reach it | Status | Notes |
|---|---|---|---|---|
| `01-dashboard-full-light.png` | Whole dashboard (light theme): header, summary cards, watchlist, yield comparison, news, sources | Open the site root | captured | synthetic demo data |
| `02-header-market-status-alerts-theme.png` | Header: navigation, NSE/BSE market-status badge (with 'calendar unverified'), Alerts button, theme switch | Top of any page | captured | synthetic; the calendar flag is real: the shipped 2026 holidays are unverified |
| `03-summary-cards.png` | Summary cards | Under the header | captured | synthetic |
| `04-watchlist-table.png` | Watchlist table with n/a and withheld states | Watchlist section | captured | synthetic |
| `05-watchlist-sorted-yield-desc.png` | Sorted by headline yield, descending; unavailable values last (a display sort, not a ranking) | Click 'Headline TTM yield' twice | captured | synthetic |
| `06-watchlist-starred-only.png` | Starred-only filter | Star a row, tick 'Starred only' | captured | synthetic |
| `07-filters-etf-search.png` | Type filter (ETF) plus text search ('gold') | Type = ETF; search box | captured | synthetic |
| `08-empty-state-no-results.png` | Empty state with a 'Clear filters' action | Search for text that matches nothing | captured | synthetic |
| `09-export-csv-control.png` | Filter toolbar with the Export CSV control; the downloaded file is attached as export-sample.csv | Click 'Export CSV' | captured | synthetic; a browser download has no page, so the file is attached |
| `10-drawer-invit.png` | Detail drawer (InvIT): price and headline-yield trend, distribution per payment, component cards (interest, dividend, return of capital), metrics with status and flags | Click the watchlist row (Enter works too) | captured | synthetic |
| `11-drawer-reit-discrepancy.png` | Detail drawer (REIT): rental-income component, open cross-source discrepancy, withheld figures, related announcement | Click the watchlist row (Enter works too) | captured | synthetic discrepancy created by irie.demo |
| `12-drawer-etf-holdings.png` | Detail drawer (ETF): NAV history, premium/discount, top-10 holdings; no income/capital split exists for an ETF | Click the watchlist row (Enter works too) | captured | synthetic |
| `13-drawer-split-unavailable.png` | Detail drawer where components are not disclosed: the split is explained as unavailable, never estimated | Click the watchlist row (Enter works too) | captured | synthetic |
| `14-yield-comparison.png` | Yield comparison grouped by type, income vs capital repayment stacked | Compare section | captured | synthetic |
| `15-alert-center-empty.png` | Alert Center modal, empty state: instrument, trigger, threshold, sound, browser-sound switch | Header > Alerts | captured | synthetic |
| `16-alert-center-active-and-triggered.png` | Alert Center with one TRIGGERED and two ACTIVE alerts, created/triggered timestamps (IST), per-alert sound, Re-arm/Delete | Add alerts | captured | synthetic; thresholds chosen for the demo data |
| `17-alert-banner-and-badge.png` | Triggered-alert banner on the page and the badge on the Alerts button | After an alert triggers | captured | synthetic |
| `18-news-all.png` | News & scrip announcements: All news (each item SYNTHETIC-labelled, with source, IST timestamp, headline, summary, original-source link) | News section | captured | synthetic headlines; links point to a reserved .invalid host |
| `19-news-filter-reits.png` | News filter: REITs | News section filter buttons | captured | synthetic |
| `20-news-filter-invits-infrastructure.png` | News filter: InvITs & infrastructure | News section filter buttons | captured | synthetic |
| `21-news-filter-corporate-announcements.png` | News filter: Corporate announcements | News section filter buttons | captured | synthetic |
| `22-sources-freshness-schedule.png` | Data sources: access, display-cleared flag, schedule, next attempt, freshness, last attempt/success, observed-through | Sources section | captured | synthetic demo sources only |
| `23-dashboard-full-dark.png` | Dark theme (whole page) | Header > Theme | captured | synthetic |
| `24-nothing-cleared-public-build.png` | Public build when no source is cleared for display: all values withheld, news withheld with an honest explanation | Build with display_cleared=false | captured | synthetic; demonstrates the licence gate |
| `25-error-data-missing.png` | Error state with Retry when data.json cannot be loaded | Serve the site without data.json | captured | synthetic site, data file removed |
| `26-mobile-390px-full.png` | Mobile layout (390 px): condensed table columns, stacked header | Narrow viewport | captured | synthetic |
| `27-mobile-drawer.png` | Detail drawer on mobile (full width) | Tap a row on a narrow viewport | captured | synthetic |
| - | Push or e-mail alert delivery | - | NOT IMPLEMENTED | not implemented: needs a server and recipient data; alerts run in the open browser tab only |
| - | G-Sec benchmark and spread columns | - | NOT IMPLEMENTED | not implemented: no cleared benchmark source |
