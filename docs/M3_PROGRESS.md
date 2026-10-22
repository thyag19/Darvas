# M3 progress (work in progress; paused mid-milestone)

## Done and committed
- **Step 1, "before" screenshots**: `tools/capture_screenshots.py` + `artifacts/screenshots/before/` (17 captured, 4 views listed NOT IMPLEMENTED:
  alert modal, news panel, market-status, theme switch). Synthetic demo data only. README in that folder.
- **Step 2, scheduler core (untested so far)**: `irie/market_calendar.py` (Asia/Kolkata, weekends, holidays, special sessions, fail-closed when a year
  is not loaded), `config/market_calendar.json` (2026 holidays from broker pages, `verified:false`, must be checked against the NSE/BSE circular),
  `irie/scheduler.py` (hourly in-session market polling; once-daily off-hours check; `local` schedule for the inbox), schedule fields in
  `irie/sources.py` / `config/sources.json`, `run_cycle(calendar=...)` integration, freshness judged against last close / daily slot.
- Importers and metric added: `news_*.csv`, `holdings_*.csv`, ETF `holdings_top10_weight`; schema `news_item`, `retrieval_log.window_class/note`.
- Existing 117 tests still pass.

## Not done yet
1. Fake-clock tests for market-hours scheduling (sessions, holiday, weekend, special session, daily slot, missing calendar year, freshness over weekend, skip-log dedupe); update `build_dataset`/CLI to pass the calendar.
2. Export: news, holdings, yield-trend and component breakdown, schedule/next-attempt, synthetic flag; demo news + holdings.
3. UI redesign (original palette; Alert Center modal with timestamps/persistence/sound; news panel with 4 filters; drawer detail; empty/error states; responsive; theme).
4. Rewrite e2e tests for the new UI; "after" screenshots (`--out artifacts/screenshots/after`).
5. `docs/DATA_SOURCES_FEASIBILITY.md` (research already gathered this session; see Phase 2 report plus: DhanHQ data API is a paid subscription per its FAQ, SEBI site allows reproduction only with permission, RBI disclaimer requires permission to link/frame, BSE/NSE terms unchanged, Yahoo terms bar commercial reuse).
6. Update M2/M3 docs, final report, commit hash.
