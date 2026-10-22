# M1 Implementation Report

Scope: data model, calculation engine, regression tests and technical foundation. M1 only. No live acquisition, no
scraping, no deployment, no ranking, tax, forecast or advice logic, and no licence or access is claimed.

## Result
- **82 tests pass** (`python -m pytest tests`, 0.2 s). Without the local fixtures: 62 pass, 20 skip (see "Public repo" below).
- The workbook's audited results are reproduced **independently** from the 398 raw distribution rows for all 26 InvITs:
  TTM DPU, payment count, headline and component yields and shares, YoY, payment CV, largest-payment share, history check,
  premium to NAV, plus portfolio XIRR (workbook 19.8054%, engine within 1e-7) and the lot ledger (cost, market value,
  distributions, capital repayment received). Tolerance for ratios is 1e-9.
- Mutation checks: shortening the window, tightening the reconciliation tolerance, and disabling the unverified-source flag
  each make tests fail. **Honest limit:** shortening the window by one day is caught only by the synthetic boundary test,
  not by the 26-trust regression, because no fixture event lies on a window edge (documented and tested).

## What was built
| Deliverable | Where |
|---|---|
| Extensible schema (REIT/InvIT/ETF, observations, distributions + components, sources, import audit) | `irie/schema.sql`, `irie/models.py` |
| Instrument-specific calculations | `irie/calc/distributions.py` (REIT+InvIT), `valuation.py`, `etf.py`, `returns.py` |
| Metric applicability registry (no universal yield) | `irie/registry.py` |
| Validating importers with explicit rejected/ambiguous reporting | `irie/importing.py`, `irie/cli.py` |
| Provenance and quality status carried through | `MetricResult` (source ids, flags, reasons), `publish_decision` |
| SQLite round-trip repository | `irie/storage.py` |
| Fixture extraction (read-only on workbook) | `tools/extract_workbook_fixtures.py` |
| Docs | `docs/M1_TECHNICAL.md` (schema, definitions, assumptions, limitations, interfaces) |

## Phase 1 defects addressed
No ranking/score exists (C1). Capital repayment is always shown beside the headline, or the reason it cannot be (C2).
Tax and forward yield are not implemented (C3, C4). Unavailable data is `UNAVAILABLE`, never zero; the zero-yield guard
tests the TTM count (C5). One definition per metric (C6). Income-only growth added (C7). Dates are explicit; inputs dated
after `as_of` are rejected (C10). Aggregator/unknown-source amounts raise the blocking flag `UNVERIFIED_SOURCE`; on the
seed this flags exactly the two trusts the workbook itself graded "Aggregator". Seed import: 398 rows read, 398 accepted,
0 rejected, 5 accepted-for-review (3 record-date gaps, 2 same-ex-date records for Capital Infra Trust), 48 informational
notes on aggregator-sourced amounts.

## Known limitations
- Regression proves formulas, not inputs; seed provenance is unverified (`audit/evidence` was not supplied).
- Single `as_of` in the regression fixture.
- REIT and ETF methodologies are defined and unit-tested on **synthetic** data only (no REIT/ETF seed data exists).
  ETFs: no holdings, expense ratio, tracking error, YTM/duration or iNAV metrics; debt ETFs get premium/discount and NAV return only.
- NDCF payout, forward yield and ranking are intentionally absent.
- Schema validated on SQLite only; PostgreSQL not exercised.
- Thresholds (3-day price staleness, 270-day NAV staleness, Rs 0.0051 tolerance, 5-day NAV gap) are configurable defaults, not regulatory values.
- Allowed component types per instrument are a modelling choice; REIT filings were not inspected.
- Prices/NAV/leverage in the seed are one snapshot each; there is no price history yet.

## Public repo: fixtures are not committed
The GitHub repository `thyag19/Darvas` is **public** (checked 22-Oct-2026). The regression fixtures contain third-party
sourced data (exchange-text-derived distribution records, aggregator amounts, ISINs, prices), and you ruled out
redistributing third-party data, so `tests/fixtures/invit_workbook_v4/` is **git-ignored and was not pushed**. It exists
only in this session's working copy. If the repo is made private, or you clear the data for display, remove the ignore line.
Anyone without the fixtures can regenerate them from the workbook with the extraction tool.

## Modified-file inventory
No existing file was modified or deleted. The workbook was opened read-only and not copied into the repository.
New files: `.gitignore`, `pyproject.toml`, `M1_IMPLEMENTATION_REPORT.md`, `docs/M1_TECHNICAL.md`, `irie/` (13 files incl.
`calc/`, `schema.sql`), `tests/` (7 test/helper files), `tools/extract_workbook_fixtures.py`. Git-ignored, local only:
`tests/fixtures/invit_workbook_v4/` (9 files). About 2,500 lines including tests and SQL.

## Claude usage
Not verifiable from inside this session (`/cost` is not available to me). Please run `/cost`. I have no basis for a dollar
figure and will not estimate one.

## Remaining blockers for M2 and public deployment
1. **Data display rights** for exchange, AMFI and index data remain uncleared (Phase 2 B1); every seed source is `display_cleared = False`.
2. **Source reachability** from the eventual runtime is untested (B2); no acquirer exists by design.
3. **REIT and ETF data sources** not yet identified or verified (B3); methodologies exist but have no real data.
4. **Index-level licensing** for ETF tracking difference (B4).
5. **SEBI advice/research position and legal review** of disclaimers (B5); ranking stays out.
6. **Seed provenance** unverified (B6); the seed is the workbook's typed data.
7. **Public repo vs. fixtures:** decide whether to make the repo private or keep fixtures local.
8. **PostgreSQL** run of `schema.sql`, hosting/domain choices, and the static JSON export are all M2 work.

M2 and live ingestion have not been started. I'm stopping here for your review.
