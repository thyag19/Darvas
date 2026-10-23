# Yield Atlas dashboard (M3)

Static HTML/CSS/JS in `irie/web`, no framework, no third-party requests, strict CSP, all text inserted via `textContent`, links limited to http(s).
It renders `data.json` (built by `irie.export`) and computes nothing; the engine does. Original visual identity: warm parchment and ink, a serif
display face for headings, and only three data colours: teal = income, ochre = other income, brick = returned capital, slate = split unavailable.
Light and dark themes (persisted). The supplied reference screenshots were used for functional scope only.

| Area | What it does |
|---|---|
| Header | Navigation, **market-status badge** (open/closed at generation time, holiday or weekend reason, "calendar unverified" until the operator verifies it), Alert Center button with triggered-count badge, theme switch |
| Overview | Six summary cards (counts by type, published yields, split-unavailable, values withheld, open discrepancies, sources fresh) |
| Watchlist | Search by name/key/ISIN, type and ETF-category filters, "yield shown", starred-only (persisted), sortable columns (unavailable always last; no ranking), CSV export of the filtered view, empty state with Clear filters, click or Enter opens the detail drawer |
| Detail drawer | KPIs; price and headline-TTM-yield trend (two axes, only where a full trailing year of verified payments is on record); distribution per payment stacked by component; **component cards** (interest, dividend, rental for REITs, other income, return of capital with the note that it is returned capital, not income) or an explicit "not available" explanation; ETF NAV history, premium/discount, top-10 holdings; metrics with status/flags/reasons/sources; open discrepancies; related announcements; retrieval vs observation times |
| Compare | Yield bars grouped by instrument type, income vs capital stacked |
| News & scrip announcements | All news / REITs / InvITs & infrastructure / Corporate announcements; source, IST timestamp, headline, summary, original-source link (`rel=noopener noreferrer`); `SYNTHETIC` label on invented items; honest empty states (no feed connected / items withheld because their source is not display-cleared / none in category) |
| Alert Center (modal) | Per-instrument or all-instrument alerts: yield above/below, premium to NAV above/below, capital-repayment share above, last price above/below, price data older than N hours; per-alert sound (chime, beep, double tick, silent); browser-sound switch (browsers require a user gesture); ACTIVE / TRIGGERED state with created and triggered timestamps (IST); re-arm and delete; persisted in the browser; evaluated on load and on each 5-minute data refresh, only on published, flag-free figures; sound plays once per transition |
| Sources | Access, display-cleared, schedule, next attempt, freshness, last attempt/status/success, observed-through, failures |
| Resilience | Load-failure screen with Retry; refresh failure keeps the last data and warns; stale-data warning after 36 h; responsive (tested at 390 px: no horizontal page overflow) |

Not implemented: push/e-mail alerts (need a server and recipient data), G-Sec benchmark/spread columns (no cleared benchmark source), live news (no cleared feed).
Screenshots of every view are in `artifacts/screenshots/after/` (synthetic data; README lists how to reach each).
