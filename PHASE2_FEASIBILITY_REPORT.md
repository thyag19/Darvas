# Phase 2: Data and Deployment Feasibility

Date: 22-Oct-2026. Builds on `AUDIT_REPORT.md` (Phase 1), which is not repeated here. No workbook, project file, account, domain or production resource was touched, and nothing was deployed or purchased.

## 0. How to read this report

**Evidence labels**
- **[P]** Primary source read directly. **None** of the findings below are [P]. The fetch tool could not resolve `nseindia.com`, `nsearchives.nseindia.com` or `amfiindia.com` (DNS error), and Phase 1 found the same hosts unreachable from this container.
- **[S]** Reported in a search-result summary of the cited page, not read in full. These are the strongest evidence I have, and every one needs confirming on the live page.
- **[T]** Third-party commentary (law firms, blogs, comparison sites). Weaker than [S].
- **[A]** My assumption or estimate. Not sourced.

**Access date for every web source below: 22-Oct-2026.**

**Limits of this research**
- It was time-boxed to about 20 web lookups.
- I did not research REIT-specific or ETF-specific data sources in depth.
- Costs are indicative and must be re-checked on each vendor's live pricing page.
- I cannot see `/cost` from inside this session, so I report no Claude usage figure. Please run `/cost` yourself.

---

## 1. Source-by-source feasibility and licensing

### 1.1 Summary table

| Source | Provides | Access method | Licensing and redistribution finding | Verdict |
|---|---|---|---|---|
| **NSE** (website, corporate-action and quote endpoints, archives) | Prices, corporate actions (incl. InvIT/REIT distribution text), listings | Website, undocumented JSON endpoints, downloadable files | Terms of Use require written permission to copy, store or redistribute content, and bar aggregating content not offered for download [S]. The historical-data portal bars scraping, mining and harvesting without express written consent [S]. Market data is governed by a separate Data Sharing and Usage Policy under which NSE is the "sole owner" and authorises redistribution through subscription agreements [S]. | **Blocker for public republication until a licence, written permission or counsel opinion exists.** Phase 1's workbook used these endpoints via browser sessions. |
| **BSE** | Prices, ex-dates for BSE-only trusts | Website and API endpoints | A BSE disclaimer page says information must not be "reproduced, redistributed, or passed on in any form" [S]. I found nothing on BSE market-data licensing or fees [S]. | **Blocker, same as NSE.** Licensing route unknown. |
| **AMFI** | Daily scheme NAVs, which include ETFs [S, inferred from one example; verify] | `NAVAll.txt`, a daily text file, per one secondary source [T] | AMFI terms grant a limited right for **personal and non-commercial use only**, bar publishing or deriving from site material, and say significant portions may not be stored electronically [S]. Other use needs written agreement [S, my reading]. | **Needs written permission for a commercial public site.** Strong fit technically, weak fit legally. |
| **SEBI** (registries, regulations, circulars) | Registered REIT/InvIT/MF lists, regulatory text | Website | Terms not researched [A]. Regulatory text is public, but reuse terms are unverified. | **Usable for reference and the universe list; confirm terms.** |
| **Issuer websites and filings** (REIT, InvIT, AMC) | Distribution notices, NDCF, results, NAV and valuation reports, leverage, ETF portfolios and factsheets | PDFs and web pages; the same filings also appear on NSE and BSE | Issuer-owned content; permissions not researched [A]. Filings are legally mandated disclosures, but that does not itself grant a redistribution right [A, counsel]. | **Best long-term source for components, NAV and gearing.** Manual-assisted extraction with a review queue. Permission still needs confirming. |
| **AMC portfolio disclosures** (ETF holdings) | Month-end and half-year portfolios with ISINs in downloadable spreadsheets, on AMC and AMFI sites, per an amended SEBI circular [S, 2018 amendment; current rule not confirmed] | AMC websites | Per-AMC terms unknown [A] | **Feasible in principle. Monthly cadence at best.** Per-AMC formats vary [A]. |
| **Index providers** (NSE Indices, BSE Indices) | Index levels, needed for ETF tracking error | Website | NSE Indices has **separate** terms of use [S]; content not read | **Likely not freely usable. Treat tracking error as blocked until licensed.** |
| **INDmoney aggregator** (used in v1, source S1) | Aggregator amounts | Website | Not researched [A] | **Do not use for published, scored or ranked figures.** Phase 1 already marked it unreliable. |
| **Commercial vendors / exchange data licences** | Licensed feeds | Contract | **Pricing and terms not researched; I will not guess them.** | **Candidate fix for the licensing blocker. Needs quotes.** |

### 1.2 Key points behind the table
- **NSE.** [S: NSE Terms of Use](https://www.nseindia.com/nse-terms-of-use), [S: NSE Data Policy](https://www.nseindia.com/market-data/nse-data-policy), [S: NSE Data Sharing and Usage Policy PDF](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/NSE_Data_Sharing%26Usage_Policy.pdf), [S: NSE Data & Analytics terms](https://dotexdata.nseindia.com/TermsAndConditions/TermsofUse.pdf).
  - A 2014 press report records NSE warning members about unauthorised redistribution, including in charting tools [T: Business Standard](https://www.business-standard.com/amp/article/pti-stories/nse-cautions-members-about-illegal-distribution-of-market-data-114061901100_1.html).
  - I could not confirm whether delayed or end-of-day display on a website falls under a lighter licence category.
- **BSE.** [S: BSE Terms](https://bseindia.com/static/about/Terms_condition.htm) (software terms only) and [S: BSE disclaimer](https://bseindia.com/static/fpi/Disclaimer.aspx).
- **AMFI.** [S: AMFI Terms of Use](https://www.amfiindia.com/terms-of-use). The `NAVAll.txt` URL and field layout come only from a secondary tool description [T: amfi-nav-extractor](https://github.com/fuzail-pixel/amfi-nav-extractor), so confirm the live file and its fields.
- **AMC portfolio disclosure rule.** [S: SEBI circular (2018 amendment, as summarised)](https://www.sebi.gov.in/sebi_data/attachdocs/jun-2018/1528207366367.pdf). The current consolidated rule was not confirmed.

### 1.3 Verified versus assumed
- **Established in this project [V, Phase 1].**
  - The workbook's 398 distribution records came from NSE, BSE and aggregator pages read by browser.
  - Those hosts are unreachable from this Claude environment.
- **Established here only as reported [S/T].** The licensing language above.
- **Not established.**
  - Whether any of these bodies would grant permission, and on what terms.
  - Whether GitHub runners or any host I would use can reach these sites.
  - Historical depth and format of AMFI and exchange files.
  - Any REIT-specific source.

---

## 2. Recommended acquisition strategy and fallbacks

**Principle:** build the platform so every datum carries a **source and licence tag**, and the UI only displays what its licence permits. Then licensing decisions change configuration, not code.

| Tier | Source path | Use | Constraint |
|---|---|---|---|
| 0 | Phase 1 workbook seed (398 records, 26-trust universe) | Seed data and golden tests | Provenance is unverified because `audit/evidence` was never supplied; the data came from the exchange and aggregator sources in section 1.1 |
| 1 | Issuer and regulatory filings, ingested with human review | Components, NAV, gearing, NDCF, ETF holdings | Slow, manual-assisted, but permissions are the clearest route and it avoids scraping exchange endpoints |
| 2 | Official bulk files (exchange end-of-day files, AMFI NAV file), only after written permission | Prices and NAV | **Gated on licence** |
| 3 | Licensed vendor or exchange data feed | Prices, corporate actions, index levels | Cost unknown; needs quotes |
| Fallback | Show derived metrics with link-outs to the issuer or exchange page instead of republishing raw series; delayed or snapshot-only data; owner-curated periodic updates | Launch without a full price feed | Reduces product value but is the lowest-risk path |

**Operational constraints**
- **Scraping.** Do not scrape any NSE, BSE or AMFI page or undocumented endpoint for a production pipeline without written permission. Using them to cross-check data internally is a lesser risk, but it is also outside what I verified.
- **Reachability.** Run a one-off reachability test from the chosen runtime (a GitHub runner, a PaaS cron job) once permission exists. Datacentre blocking is a known risk for exchange sites [A].
- **Development environment.** My cloud environment denies these hosts. To work with live data you would either change its network policy ([docs](https://code.claude.com/docs/en/cloud-environments#network-access)) or supply files. I recommend supplying files, which also keeps development independent of the licensing question.
- **Update cadence [A].** Prices daily after close, corporate actions daily, NAV and gearing on filing events, ETF holdings monthly.

---

## 3. Instrument-specific analytical requirements

Every metric returns a **value or an explicit reason it is unavailable**. Never zero, never a silent blank. Income distributions and capital repayments are separated wherever the source discloses components.

### 3.1 InvIT
| Metric | Inputs | Reliability |
|---|---|---|
| TTM distribution (total) and yield | Distribution events, price | **Reliable** where amounts are exchange- or issuer-verified (Phase 1: 21 of 26 trusts; recomputation matched the workbook exactly) |
| Income, other and capital-repayment split | Components per event | **Reliable only when components reconcile to the total and the source is verified.** Otherwise "not disclosed". |
| Capital-repayment share and adjusted cost basis | Components, purchase cost | Reliable for the same trusts |
| NDCF per unit and payout ratio | NDCF disclosures | **Partly reliable.** SEBI standardised NDCF computation in Dec 2023 effective 1-Apr-2024 [S: [Business Standard](https://www.business-standard.com/markets/news/sebi-lays-down-framework-for-calculation-of-net-distributable-cash-flows-123120600925_1.html), [JSA](https://www.jsalaw.com/?p=49909)], so earlier periods are not comparable [A] |
| P/NAV | NAV and NAV date | Reliable for the 17 trusts with verified NAV; show the NAV date; staleness threshold |
| Leverage (net debt/AUM) | Issuer filings | **Not comparable across trusts today.** Definitions differ (Phase 1). Show per-trust, per-definition. |
| Forward yield | Run-rate | **Not reliable.** Drop it, or label it "run-rate illustration" only. |
| Remaining concession life, asset class, debt maturity, ratings | Issuer PDFs | Manual extraction only [A] |

Regulatory context useful for interpretation [S/T, check current text]:
- Publicly listed InvITs must distribute at least 90% of NDCF, at least half-yearly [T: [SEBI PR 89/2014](https://www.sebi.gov.in/sebi_data/docfiles/28905_t.html), [Khaitan](https://khaitanco.com/thought-leadership/sebi-relaxes-norms-for-INVITS)].
- The borrowing cap was 49% and was raised to 70% in 2019 subject to conditions including AAA rating [T].
- Both are secondary summaries, not the current regulation text.

### 3.2 REIT
| Metric | Reliability |
|---|---|
| TTM distribution, yield, and split into interest, dividend, rental and capital components | **Plausible** if REIT filings disclose components as InvIT filings do [A, unverified]. Reuse the same engine. |
| NDCF per unit, payout | As InvIT; the Dec 2023 framework covers REITs too [S] |
| P/NAV, LTV (net debt/GAV) | Computable from issuer filings. REIT borrowing cap is 49%, with approval and rating above 25% [S: [ICRA methodology](https://www.icra.in/Rating/GetRatingMethodologyFile/512~Real%20Estate%20Investment%20Trusts)], so LTV is comparable in definition [A, verify]. |
| Occupancy, WALE, rent reversion, tenant concentration, NOI yield, implied cap rate | **Manual extraction from presentations and valuation reports.** Not automatable reliably; treat as curated fields with a source and date. |
| Unit dilution adjustments | Needs unit-count history from filings |

### 3.3 ETFs (by category)
| Category | Reliable from available data | Not reliably calculable |
|---|---|---|
| Equity index / broad | NAV-based returns (needs AMFI-type NAV history and permission), expense ratio and AUM from AMC disclosures, holdings | **Tracking error and tracking difference** need licensed index levels. **Intraday premium/discount** needs a licensed iNAV feed. [A] |
| Sector / thematic / factor | Same, plus holdings concentration | Same |
| Gold / silver | Price vs NAV premium or discount (EOD), expense ratio | Backing details beyond what AMCs disclose |
| Debt / liquid / G-sec / target-maturity | YTM, duration, credit quality from AMC factsheets (manual extraction) | Cross-fund comparability without a consistent source |
| International | Premium/discount EOD, currency effect | Underlying-index levels (licensing) |

- **Yield.** Most ETFs distribute nothing [A]. Show no distribution yield unless the scheme pays IDCW, in which case show it as informational and **never** as an index dividend yield.
- **No income/capital split** exists for ETF distributions [A].
- **Holdings.** AMC disclosures are monthly at best [S, 2018 circular].

### 3.4 Data model and engine (design requirements)
- **`instrument`** with `type` (InvIT, REIT, ETF) and `category`, plus **`listing`** (exchange, symbol, ISIN).
- **`distribution_event`** (ex-date, record date, total per unit, status) with **`distribution_component`** (type enum, amount, classification source). Component types are typed, never a free-text label.
- **`price_eod`**, **`nav`** (typed: fair-value, book, fund NAV), **`leverage`** (with a definition enum), **`unit_count`**, **`holding`** (ETF, as-of, ISIN, weight), **`fundamental`** (typed key, period, definition, value, status).
- **`source_document`** (URL, retrieved-at, hash, **licence tag, `can_display`**), and **`data_quality_flag`**.
- **Metric registry:** each metric declares which instrument types and categories it applies to and which inputs it needs. The engine returns a value or a reason. This is what prevents identical metrics being forced onto every instrument.
- **Regression references.** Keep the Phase 1 verified results as golden tests: TTM DPU, component sums, CV, YoY for all 26 trusts, and portfolio XIRR of 19.8054%.
- **Phase 1 defects to fix in the engine.**
  - C1, C2: no ranking; always show the split.
  - C5: guard on the TTM count.
  - C6: one definition of capital share.
  - C3: no tax model.

---

## 4. Architecture evaluation and hosting options

### 4.1 FastAPI + managed Postgres + static frontend: assessment
It works, but it is more than the first release needs. The dataset is tiny (398 records so far), read-heavy and updated once a day. My rough estimate [A] is that all three classes, five years of daily prices, fit well under a few hundred MB.

**Recommended shape: publish-time snapshots first, API later.**
1. A daily job writes to Postgres (system of record), runs validation, and exports JSON.
2. A static site on a CDN serves the JSON. Calculators run in the browser.
3. Add a FastAPI service only when a feature needs server-side queries.

Benefits: no always-on server to secure, near-zero hosting cost, little to attack. Cost: interactivity beyond precomputed data waits for the API.

### 4.2 Free-tier facts and limits

| Service | Finding | Evidence |
|---|---|---|
| **Neon Postgres (free)** | Storage 0.5 GB or 1 GB (sources conflict; one digest dates a doubling to the week of 28-Sep-2026); 100 compute-hours a month; scales to zero after 5 minutes; compute **suspends when a monthly limit is hit**; 10 branches; short restore window | [T/S: [Neon pricing](https://neon.com/pricing), [JetAdmin](https://www.jetadmin.io/blog/neon-pricing/)]. Verify on Neon's page. |
| **Supabase (free)** | 500 MB database, 2 active projects, **paused after 1 week of inactivity**; Pro from $25 a month with 8 GB | [T/S: [Supabase pricing](https://supabase.com/pricing.md)] |
| **Render (free)** | Free web services spin down after 15 minutes idle, up to about a minute to wake, no persistent disk. **Free Postgres expires after 30 days** (current docs), 1 GB. Unsuitable for the database. | [S: [Render docs](https://render.com/docs/free)] |
| **Fly.io** | No ongoing free tier for new organisations; smallest machine about $1.94 a month (official page); managed Postgres reported from about $38 a month (third-party) | [S/T: [Fly pricing](https://fly.io/docs/about/pricing/)] |
| **Cloudflare Pages (free)** | 500 builds a month (per-project vs per-account disputed), 20,000 files, 25 MiB per file. Bandwidth "unmetered" appears only in third-party sources. Pages Functions share a 100,000 requests/day Workers quota (secondary). | [S: [Cloudflare limits](https://developers.cloudflare.com/pages/platform/limits)] |
| **GitHub Actions cron** | In **public** repos scheduled workflows are disabled after 60 days without repository activity; forks have schedules disabled. Free-minute allowances not verified. | [S: [GitHub docs](https://docs.github.com/en/enterprise-server@3.20/actions/using-workflows/disabling-and-enabling-a-workflow)] |
| **UptimeRobot (free)** | 50 monitors, 5-minute interval. A non-commercial restriction is not confirmed either way; read its terms. | [S: [UptimeRobot pricing](https://uptimerobot.com/pricing.md)] |
| **Sentry (free)** | One user, 5,000 errors a month; Slack alerts need a paid plan (competitor claim) | [T: [Last9](https://last9.io/blog/sentry-pricing/), [Bugsink](https://www.bugsink.com/blog/does-sentry-free-plan-support-slack-alerts/)] |

### 4.3 Hosting options

| Option | Stack | Fit | Main risk |
|---|---|---|---|
| **A. Lean (recommended start)** | Neon free Postgres + daily job + static site on Cloudflare Pages + client-side calculators | Cheapest and smallest attack surface | Neon limits may suspend the database; a public-repo cron can silently stop after 60 days idle; no live API |
| **B. Standard** | A + small always-on API on a paid PaaS instance + paid DB tier | Needed once an API or heavier queries are required | Monthly cost; more to operate |
| **C. Managed all-in-one** | Supabase Pro | Fewer vendors | $25 a month floor and vendor lock-in |

Recommendation: **A for launch**, with B as the planned upgrade, and paid upgrades pre-approved so the site never goes dark on a free-tier limit.

---

## 5. Operating cost estimates (separate from Claude)

All figures indicative [A]. Re-check every price at purchase time. Currency conversions are approximate.

| Item | Lean (A) | Standard (B) | Basis |
|---|---|---|---|
| Domain | About ₹625 a year (about $7), or about $6 elsewhere | Same | [T: [Domain India](https://www.domainindia.com/login/announcements/52), [Spaceship](https://www.spaceship.com/domains/cctld/in/)]. A `.com` price was not researched. |
| Static hosting and CDN | $0 | $0 | Cloudflare Pages free limits above |
| Database | $0 (free tier, with suspension risk) | Roughly $5–20 a month [A] | Neon paid compute is reported at about $0.106 per CU-hour [T]; always-on 0.25 CU is roughly $19 a month by my arithmetic |
| API compute | None | About $2–7 a month | Fly smallest machine about $1.94 [S]; a $7 PaaS starter tier is reported [T] |
| Scheduled jobs | $0 on GitHub Actions (with the 60-day caveat) | Included in PaaS cron or free | |
| Monitoring | $0 (UptimeRobot and Sentry free) | $0–10 | Free-tier limits above |
| **Data licensing** | **Unknown** | **Unknown** | **No price researched. Request quotes from NSE Data & Analytics and BSE, and ask AMFI about permission.** This is the one cost that could dominate. |
| **Indicative total excluding licences** | **About $0–1 a month plus domain** | **About $10–35 a month** | |

Also budget for professional fees (legal and tax review). I have not priced them.

---

## 6. Legal review checklist (for qualified professionals)

I am not offering legal conclusions. Items below are questions for counsel, with the finding that prompted each.

1. **Exchange data redistribution.**
   - NSE and BSE terms as reported restrict copying and redistribution [S].
   - Ask: what may a public site display (end-of-day prices, corporate-action facts, derived yields)? What licence category and fees apply? Is derived or aggregated output treated differently?
2. **AMFI.** Terms permit personal, non-commercial use [S]. Ask whether a written agreement is needed for NAV display.
3. **Issuer and AMC documents.** Confirm permission to extract and republish disclosed figures, and how to attribute.
4. **Index data.** NSE Indices has separate terms [S]. Ask what is needed for tracking-error calculations.
5. **Scraping and automated access.** Review the "systematic or automated collection" prohibition [S] against any planned acquisition method, and the legal position of the workbook's earlier browser-based collection.
6. **Investment-advice and research regulation.**
   - SEBI's research analyst regulations prohibit holding out as a research analyst without registration, with disclosure and rating-system rules [S: [SEBI PR](https://www.sebi.gov.in/media/press-releases/nov-2014/commencement-of-sebi-research-analysts-regulations-2014_28475.html), [compliancecalendar.in](https://www.compliancecalendar.in/learn/who-needs-research-analyst-registration-under-sebi-rules)].
   - Ask whether factual metrics are outside scope, and what, if anything, a score, ranking, "quality" label or comparison would trigger. The search found nothing on an unregistered website publishing ratings, so this is unresolved.
   - Also review the Investment Advisers regulations [A].
7. **Privacy.**
   - The Digital Personal Data Protection Rules were notified on 13-Nov-2025. The operative notice, consent and security rules take effect on 13-May-2027 [T: [Mondaq](https://www.mondaq.com/india/data-protection/1708164/digital-personal-data-protection-rules-2025-notified), [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/)].
   - A no-accounts launch minimises exposure, but confirm obligations for server logs, analytics and any contact form.
8. **Tax content.** The Phase 1 model is unverified. Keep tax output out of the product unless a qualified professional reviews it.
9. **Disclaimers, terms of use, privacy notice, attribution, and a corrections or takedown process.**
10. **Corporate structure and who contracts for data licences** (individual versus entity).

---

## 7. Roadmap and budget

**Claude budget: $75 total. Target at most $54 for implementation and keep $21 in reserve.** The figures below are my estimates [A]. I cannot see actual spend, so check `/cost` after each milestone.

| Milestone | Scope | Est. Claude spend |
|---|---|---|
| **M0. Gates (no build)** | Owner decisions, licence enquiries, counsel briefing, host choice | $1 |
| **M1. Foundation** | Schema (section 3.4), metric registry, calculation engine, import of the workbook seed, golden tests reproducing Phase 1 results, fixes for C1–C6. File-based ingestion only. | $11 |
| **M2. InvIT release** | Static site and JSON export, trust pages with component split, quality badges, methodology and sources pages, freshness stamp, disclaimers, CI, deploy to Lean option. **No ranking.** | $17 |
| **M3. REITs** | REIT instruments and components through the same engine; curated fundamentals fields; reviewed ingestion for the few trusts | $9 |
| **M4. ETFs** | ETF categories, NAV-based returns where licensed data exists, holdings from AMC disclosures, applicability rules for yield | $12 |
| **Hardening and security review** | Validation, monitoring, backups, restore drill | $4 |
| **Total** | | **$54** |
| Reserve | | $21 |

Notes:
- M3 and M4 depend on data permissions and sources I have not verified. If those remain unresolved, M3 and M4 ship with whatever the owner-supplied or permitted data supports, and the registry shows "not available" for the rest.
- Ranking stays out until a validated methodology and its inputs exist and counsel has reviewed it.

---

## 8. Unresolved blockers and go/no-go criteria

### 8.1 Blockers
| ID | Blocker | Why it matters |
|---|---|---|
| B1 | **No confirmed right to republish exchange, AMFI or index data publicly** | Could force a licence fee, a reduced feature set, or link-outs |
| B2 | **Source reachability from the chosen runtime is untested.** My own environment is blocked. | The daily pipeline may not run where hosted |
| B3 | **REIT and ETF sources not researched in depth** | Milestones M3 and M4 rest on assumptions |
| B4 | **Index-level licensing for tracking error** | An ETF headline metric may be unavailable |
| B5 | **SEBI advice and research position unresolved** | Governs whether any scoring or comparison can ever ship |
| B6 | **Phase 1 data provenance unverified** (`audit/evidence` and v1–v3 workbooks absent) | Seed data cannot be called verified |
| B7 | **Phase 1 collection used undocumented endpoints under terms that, as reported, restrict automated collection** | Legal exposure for continued use |

### 8.2 Go/no-go criteria
**Implementation (M1) may start when:**
- G0. You have reviewed this report and approved the plan.
- G1. You supply the seed workbook and test fixtures as files, and accept that M1 uses no live data.
- G2. You accept no ranking and no tax output at launch.

**M2 public launch may proceed only when:**
- G3. A written position on data display rights exists (a licence, written permission, or a counsel opinion) for every source whose data the site shows, **or** the site shows only data from sources that are cleared.
- G4. The acquisition path is proven from the chosen runtime for each source, **or** an owner-supplied file path is accepted as the update method.
- G5. Counsel has reviewed the disclaimers, terms and the no-ranking position.
- G6. You approve the domain, registrar and hosting accounts, and agree paid fallbacks so free-tier limits cannot take the site offline.
- G7. The golden tests reproduce the Phase 1 results (TTM, components, XIRR) and `/cost` shows M1 spend within budget.

**Stop or re-plan if:**
- Any required source refuses permission with no licensed alternative, or the licence cost is unaffordable.
- M1 exceeds about $11 by more than 25%, without a clear reason.

---

## 9. Recommendation: proceed with constraints

**Proceed with constraints.**

- **Why proceed.** The calculation core is verified, small, and independent of licensing. A well-designed schema and metric registry makes REIT and ETF support a configuration exercise. Hosting can be near-free. The cost and risk sit in data rights, not in engineering.
- **Why constrain.** I found no confirmed right to republish exchange, AMFI or index data on a public commercial site. The terms I found, as reported, point the other way. The feasibility of an automated pipeline is untested. Building a live scraper or launching publicly now would be building on an unresolved legal and access question.

**Constraints:**
1. Start only M1 (engine, schema, golden tests, file-based seed). It needs no live data and no licence.
2. Run the licensing and legal enquiries in parallel.
3. Do not build the live pipeline or deploy publicly until G3–G6 pass.
4. Keep ranking, tax output and any scoring out.
5. Check `/cost` at each milestone gate.

**I have stopped here and will not begin implementation until you review this report.**

---

## 10. Source list (all accessed 22-Oct-2026)

| Source | Cited for |
|---|---|
| [NSE Terms of Use](https://www.nseindia.com/nse-terms-of-use) [S] | Copying, storing, redistribution |
| [NSE Data Policy](https://www.nseindia.com/market-data/nse-data-policy) [S] | Market data ownership |
| [NSE Data Sharing and Usage Policy (PDF)](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/NSE_Data_Sharing%26Usage_Policy.pdf) [S] | Licensing via subscription |
| [NSE Data & Analytics terms (PDF)](https://dotexdata.nseindia.com/TermsAndConditions/TermsofUse.pdf) [S] | Bar on automated collection |
| [Business Standard, 2014](https://www.business-standard.com/amp/article/pti-stories/nse-cautions-members-about-illegal-distribution-of-market-data-114061901100_1.html) [T] | Past NSE enforcement stance |
| [BSE Terms](https://bseindia.com/static/about/Terms_condition.htm), [BSE disclaimer](https://bseindia.com/static/fpi/Disclaimer.aspx) [S] | BSE reproduction restrictions |
| [AMFI Terms of Use](https://www.amfiindia.com/terms-of-use) [S] | Personal, non-commercial use |
| [amfi-nav-extractor](https://github.com/fuzail-pixel/amfi-nav-extractor) [T] | NAV file location and fields (unverified) |
| [SEBI circular, 2018 amendment](https://www.sebi.gov.in/sebi_data/attachdocs/jun-2018/1528207366367.pdf) [S] | AMC portfolio disclosure |
| [SEBI PR 89/2014](https://www.sebi.gov.in/sebi_data/docfiles/28905_t.html), [Khaitan](https://khaitanco.com/thought-leadership/sebi-relaxes-norms-for-INVITS) [T] | InvIT distribution and leverage rules |
| [ICRA REIT methodology](https://www.icra.in/Rating/GetRatingMethodologyFile/512~Real%20Estate%20Investment%20Trusts), [Business Standard, Dec 2023](https://www.business-standard.com/markets/news/sebi-lays-down-framework-for-calculation-of-net-distributable-cash-flows-123120600925_1.html), [JSA](https://www.jsalaw.com/?p=49909) [S/T] | REIT rules, NDCF framework |
| [SEBI RA regulations PR](https://www.sebi.gov.in/media/press-releases/nov-2014/commencement-of-sebi-research-analysts-regulations-2014_28475.html), [compliancecalendar.in](https://www.compliancecalendar.in/learn/who-needs-research-analyst-registration-under-sebi-rules) [S/T] | Research analyst registration |
| [Mondaq](https://www.mondaq.com/india/data-protection/1708164/digital-personal-data-protection-rules-2025-notified), [AZB](https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/) [T] | DPDP Rules timeline |
| [Neon pricing](https://neon.com/pricing), [JetAdmin](https://www.jetadmin.io/blog/neon-pricing/) [S/T] | Neon free tier |
| [Supabase pricing](https://supabase.com/pricing.md) [S/T] | Supabase free tier |
| [Render docs](https://render.com/docs/free) [S] | Render free limits |
| [Fly pricing](https://fly.io/docs/about/pricing/) [S/T] | Fly pricing |
| [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits) [S] | Pages limits |
| [GitHub Actions docs](https://docs.github.com/en/enterprise-server@3.20/actions/using-workflows/disabling-and-enabling-a-workflow) [S] | 60-day schedule disabling |
| [UptimeRobot pricing](https://uptimerobot.com/pricing.md) [S] | Free monitoring tier |
| [Last9](https://last9.io/blog/sentry-pricing/), [Bugsink](https://www.bugsink.com/blog/does-sentry-free-plan-support-slack-alerts/) [T] | Sentry free tier |
| [Domain India](https://www.domainindia.com/login/announcements/52), [Spaceship](https://www.spaceship.com/domains/cctld/in/) [T] | `.in` domain price |
