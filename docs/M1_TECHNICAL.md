# M1 technical documentation: `irie`

Standard-library Python (>= 3.11). No network access, no ranking, no tax, no forecasts, no advice.
Run tests: `pip install pytest && python -m pytest tests`.

## 1. Layout

| Path | Role |
|---|---|
| `irie/models.py` | Domain types: Instrument (REIT / INVIT / ETF + ETF category), Source (grade, `display_cleared`), DistributionEvent + components, PricePoint, NavPoint, LeveragePoint, Holding. |
| `irie/result.py` | `MetricResult` (value **or** status + reasons + flags + source ids), `publish_decision` gate. |
| `irie/calc/distributions.py` | Shared REIT/InvIT distribution engine (windows, component verification, yields, shares, growth, dispersion). |
| `irie/calc/valuation.py` | P/NAV, REIT net debt / GAV, reported leverage passthrough. |
| `irie/calc/etf.py` | ETF premium/discount, NAV return/CAGR, tracking difference, distribution yield (only where defined). |
| `irie/calc/returns.py` | XIRR and a lot-level distribution ledger (pure arithmetic). |
| `irie/registry.py` | Which metric applies to which instrument type/category; `compute_all(Snapshot)`. |
| `irie/importing.py` | Validating CSV importers (distributions, prices, NAVs) with an explicit report. |
| `irie/schema.sql`, `irie/storage.py` | Portable relational schema; minimal SQLite repository used to prove round-trip. |
| `irie/seed.py`, `irie/cli.py` | Load a seed bundle; `validate-distributions` and `metrics` commands. |
| `irie/interfaces.py` | Protocols for future acquisition and static export (no implementations). |
| `tools/extract_workbook_fixtures.py` | Read-only extraction of regression fixtures from the workbook. |

## 2. Schema (`irie/schema.sql`)

Design rules: missing = NULL, never 0; an included distribution must have an amount (CHECK); every observation
names a source; every source has a grade and a `display_cleared` flag that **defaults to 0**; imports are recorded
(`import_run`, `import_issue`) so nothing is silently repaired.

Tables: `source`, `source_document`, `instrument`, `listing`, `price_eod`, `nav`, `leverage`, `unit_count`,
`distribution_event` + `distribution_component`, `index_level`, `holding`, `fundamental`, `import_run`, `import_issue`.
`holding`, `fundamental`, `unit_count`, `index_level` and `source_document` are schema-only in M1 (no calculation or
importer yet).

Status: executed and constraint-tested on SQLite. **Not yet run on PostgreSQL** (it uses only portable constructs;
use `NUMERIC(18,8)` and `TIMESTAMPTZ` there).

## 3. Calculation definitions

All windows are ex-date based. `as_of` is a required argument everywhere; nothing reads the clock. TTM window =
`(as_of - 365d, as_of]`; prior window = `(as_of - 730d, as_of - 365d]`. Metrics return `OK`, `PARTIAL`,
`UNAVAILABLE` or `NOT_APPLICABLE`; never a silent zero.

### 3.1 REIT and InvIT (`calc/distributions.py`)
| Metric | Definition |
|---|---|
| `ttm_dpu` | Sum of per-unit amounts of included events in the TTM window. No events -> UNAVAILABLE (`NO_TTM_DISTRIBUTIONS`); only amount-unavailable events -> UNAVAILABLE (`ALL_AMOUNTS_UNAVAILABLE_IN_WINDOW`). Some unavailable -> value is a lower bound with flag `AMOUNT_UNAVAILABLE_IN_WINDOW`. |
| `ttm_yield` | `ttm_dpu / price`. **Headline: includes capital repayment.** Price must be positive and not dated after `as_of`; older than 3 days -> flag `PRICE_STALE` (value still shown). |
| Components | An event's split is *verified* only if the components sum to the total within Rs 0.0051 (rounding of 2-dp disclosures) **and** the amount's source grade is exchange, issuer or regulator. Coverage of the window is COMPLETE / PARTIAL / NONE. |
| `income_yield`, `other_yield`, `capital_repayment_yield`, `*_share` | Computed **only** when coverage is COMPLETE. PARTIAL -> status PARTIAL, value withheld; NONE -> UNAVAILABLE. A split is never inferred. Income = interest + dividend (+ rental for REITs). Other = other/treasury income (not assumed recurring). Capital = return of capital / SPV debt repayment / capital reduction. Complete split with no capital component -> capital = 0 (the components then add to the total). |
| `yoy_total_dpu` | `ttm / prior - 1`, only if the history check is OK. Flagged `INCLUDES_CAPITAL_REPAYMENT`. |
| `yoy_income_dpu` | Income-only growth; needs COMPLETE coverage in both windows. |
| History check | NO_DATA / NO_AMOUNTS / INCOMPLETE_UNAVAILABLE_AMOUNTS (amount-unavailable event in last 24 months) / INCOMPLETE_SHORT_HISTORY (first included record after `as_of - 730d`) / OK. |
| `payment_size_cv`, `largest_payment_share` | Descriptive only (sample std dev / mean; largest / total). Distorted by irregular tranches. |
| `premium_to_nav` | `price / NAV - 1`. NAV older than 270 days -> `NAV_STALE` (assumption carried over from the workbook, configurable); non-verified NAV -> `NAV_UNVERIFIED`. |
| `reported_leverage` | Disclosed value with its definition flag. Definitions differ by issuer; never compared across instruments. |
| `net_debt_to_gav` | REIT only: net debt / gross asset value, same filing and date; net cash allowed, GAV must be > 0. |

### 3.2 ETF (`calc/etf.py`)
ETFs get **no** income/capital split and no REIT/InvIT metric. Defined: `premium_discount_to_nav` (same-date price and NAV);
`nav_return_1y` (last NAV on or before each date within 5 days; excludes distributions, flagged for distributing schemes);
`nav_cagr` (spans >= 365 days only); `tracking_difference_1y` (fund return minus benchmark return, equity / sector-factor /
international / gold-silver categories only; **not tracking error**); `trailing_distribution_yield` (only if the scheme is
known to distribute: NOT_APPLICABLE if it does not, UNAVAILABLE if unknown).

### 3.3 Returns (`calc/returns.py`)
`xirr`: 365-day convention from the earliest flow (Excel convention), bisection; None unless both signs present.
`portfolio_ledger`: a lot receives a distribution when `purchase_date < ex_date <= as_of`; future-dated lots are excluded;
unpriced lots are listed, never valued at zero; capital repayment is reported separately (no tax effect modelled).

## 4. Phase 1 defects: how each is handled

| Phase 1 finding | M1 handling |
|---|---|
| C1 aggregator-sourced trusts ranked | No ranking exists. Aggregator/unknown-grade amounts raise blocking flag `UNVERIFIED_SOURCE`. |
| C2 headline yield hides capital repayment | Headline always travels with split-or-reason; one definition of capital share. |
| C3 tax model | Not implemented. |
| C4 mechanical forward yield | Not implemented. |
| C5 zero vs unavailable | `UNAVAILABLE` with reason; guard is on the TTM count, not lifetime records. |
| C6 duplicate/inconsistent metrics | Single definition per metric (registry). |
| C7 growth includes capital | `yoy_income_dpu` added; total growth flagged. |
| C8 20-lot cap | Ledger takes any number of lots; nothing persisted. |
| C10 mixed as-of dates | `as_of` explicit; inputs dated after it are rejected (price, NAV, leverage) or flagged (events). |
| C11 portfolio yield assumes full-window holding | Not carried over. |

## 5. Importers (`irie/importing.py`)
ISO dates only (`yyyy-mm-dd`; ambiguous forms are rejected), decimals only, blank = None. Every row is accepted, accepted
with REVIEW, or rejected, and the report (`to_json`) returns the original row with each issue. **REJECT**: missing key,
unknown instrument, missing/bad date, bad or negative number, component not allowed for the instrument type, bad
include/grade value, exact duplicate (prices/NAVs: conflicting duplicate). **REVIEW** (imported, flagged):
`INCLUDE_WITHOUT_AMOUNT` (kept as amount-unavailable), `COMPONENTS_WITHOUT_TOTAL`, `COMPONENTS_DO_NOT_RECONCILE`,
`RECORD_BEFORE_EX_DATE`, `RECORD_DATE_GAP` (> 3 days), `EX_DATE_AFTER_AS_OF`, `UNKNOWN_SOURCE_ID`,
`SAME_EX_DATE_MULTIPLE_RECORDS`. **INFO**: `UNVERIFIED_AMOUNT_SOURCE`. Event ids are content hashes, so re-imports and
re-ordering are stable.

## 6. Assumptions and limitations
- Regression proves the **formulas**, not the **inputs**: workbook inputs were typed from exchange/aggregator pages and
  their provenance (`audit/evidence`) was not supplied.
- The regression fixture pins a single `as_of` (21-Oct-2026) and no fixture event lies within a day of a window edge, so
  it cannot catch an off-by-one window length; boundaries are pinned by synthetic tests.
- Excel's XIRR is accurate to ~1e-8, so XIRR is compared at 1e-7.
- REIT methodology is defined and unit-tested on synthetic data only: no REIT data exists in the seed.
- ETF methodology is likewise synthetic-tested. No holdings, expense-ratio, tracking-error, YTM/duration, iNAV or
  intraday metrics. Debt ETFs get premium/discount and NAV return only.
- NAV staleness (270 days), price staleness (3 days), reconciliation tolerance (Rs 0.0051) and the 5-day NAV gap are
  configurable defaults, not regulatory values.
- Permitted components per instrument type are a modelling choice; REIT filings were not inspected.
- SQLite stores NUMERIC as REAL; round-trip is exact for the 4-6 dp amounts used (tested), but PostgreSQL behaviour is untested.
- No licence, data access or display right is claimed for any source; all seed sources load with `display_cleared = False`.

## 7. Regression fixtures
`tests/fixtures/invit_workbook_v4/` holds data copied from the user's workbook (distribution records parsed from exchange
text, aggregator amounts, ISINs, prices). **It is git-ignored because the repository is public and the data is third-party
sourced; it is not committed or redistributed.** Without it, the 20 regression-dependent tests skip and the other 62 run.
Regenerate locally (read-only on the workbook):
`python tools/extract_workbook_fixtures.py <InvIT_Yield_Analysis_Tool_v4.xlsx> tests/fixtures/invit_workbook_v4`
(needs `openpyxl`).

## 8. Interfaces for later milestones
- **Acquisition (M2+):** implement `irie.interfaces.Acquirer` per cleared source, emitting `RawDocument`; reuse the importers
  so live and file data share validation; store `source_document` (hash, retrieved_at) and `import_run`.
- **Static frontend:** `SnapshotExporter` writes JSON only for results where `publish_decision(...) == (True, [])`; the
  frontend never computes metrics.
- **Database:** `storage.py` is the only SQL; swap its connection for PostgreSQL after running `schema.sql` there.
- **Scheduler:** a job = fetch -> import -> compute_all(as_of) -> export; `as_of` is passed in.

### Gates (unchanged from Phase 2)
No Acquirer is to be written, and nothing published, until data access and display rights for its source are cleared.
