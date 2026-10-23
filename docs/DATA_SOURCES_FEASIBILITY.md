# Zero-cost data sources for Indian REITs, InvITs and ETFs: feasibility (M3)

Access dates: 22-Oct-2026 (web searches; Phase 2 research is reused, not repeated). **Evidence labels:** [S] reported in a search-result
summary of the cited page; [T] third-party commentary; [A] my assumption. I could not read the NSE, BSE or AMFI pages themselves (the
build environment cannot reach them), so every statement about their terms is [S] and must be confirmed on the live page.
**Conclusion: I found no zero-cost source for which automated retrieval AND public display/redistribution are established as permitted.**
Nothing here was bypassed or fabricated; the product runs on operator-supplied files and the registry fetches nothing from an uncleared source.

## Source by source
| Source | Data it could supply | Access method | History / frequency | Automated-access restriction | Public display / redistribution | Status |
|---|---|---|---|---|---|---|
| **NSE** (website, quote and corporate-action endpoints, archive files) | prices, distributions (free-text), announcements | web pages, undocumented JSON endpoints, downloadable archives | not verified here; EOD and intraday quotes | reported: scraping, mining and harvesting barred without written consent [S: [NSE data portal terms](https://dotexdata.nseindia.com/TermsAndConditions/TermsofUse.pdf)] | reported: written permission needed to copy, store or redistribute [S: [NSE Terms of Use](https://www.nseindia.com/nse-terms-of-use)]; market data licensed by subscription [S: [Data Sharing & Usage Policy](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/NSE_Data_Sharing%26Usage_Policy.pdf)] | **Blocked** pending written permission or a licence |
| **BSE** (website, announcements, scrip data) | prices, announcements, ex-dates (no amounts) | web pages, APIs | not verified | not established; no official API terms found in my search | reported: information not to be reproduced or redistributed [S: [BSE disclaimer](https://bseindia.com/static/fpi/Disclaimer.aspx)] | **Blocked** |
| **AMFI** (daily NAV file) | ETF NAVs | text file download | daily; history not verified | not established | reported: personal, non-commercial use; other use needs written agreement [S: [AMFI terms](https://www.amfiindia.com/terms-of-use)] | **Blocked** pending agreement |
| **SEBI** (registries, regulations, circulars) | universe lists, regulatory text | website | n/a | not established | reproduction free of charge **after permission requested by e-mail**, with accuracy and credit; third-party material excluded [S: [SEBI website policy](https://www.sebi.gov.in/website-policy.html)] | **Permission route exists; not requested.** Needs your decision. |
| **RBI** | G-Sec yields (benchmark) | website | n/a | not established | disclaimer requires permission to link or frame [S: [RBI disclaimer](https://rbi.org.in/commonman/English/Scripts/Disclaimer.aspx)]; reuse terms for yield data not found | **Not used** (no benchmark columns) |
| **Issuer / AMC disclosures** | distributions and components, NAV, leverage, fundamentals, ETF portfolios, announcements | PDFs and web pages, mirrored on the exchanges | per issuer; AMC portfolio disclosure is monthly or half-yearly per an amended SEBI circular [S: [SEBI circular 2018](https://www.sebi.gov.in/sebi_data/attachdocs/jun-2018/1528207366367.pdf)] | per site; not reviewed | per issuer; not reviewed | **Unknown per issuer.** Best long-term route; ask each issuer. |
| **DhanHQ Data API** (broker) | live and historical prices | authenticated API | intraday and daily history | account API | **not zero-cost**: Data API subscription is ₹499 plus tax per month [S: [Dhan FAQ](https://dhan.co/support/platforms/dhanhq-api/how-does-the-dhanhq-data-api-subscription-work/)]; redistribution terms not found | **Excluded** (cost; rights unknown) |
| **Yahoo Finance / yfinance** | prices | unofficial endpoints | daily history | automated collection outside Yahoo APIs reported as barred [T] | reuse for commercial purposes barred by Yahoo's terms [S/T: [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)]; upstream exchange data licensed by others | **Excluded** |
| **Aggregators** (e.g. the one used in the v1 workbook) | amounts, prices | web pages | varies | terms not reviewed | terms not reviewed; graded AGGREGATOR, never used for published figures | **Excluded** |
| **data.gov.in (OGDL)** | none found | portal | n/a | n/a | licence not verified; I found no relevant REIT/InvIT/ETF dataset | **No suitable dataset found** |
| **Index providers** (NSE Indices, BSE Indices) | index levels for tracking difference | website | n/a | not established | separate terms [S: [NSE Indices](https://niftyindices.com/terms-of-use)] | **Blocked**; tracking error stays out |
| **Operator-supplied files** | anything the operator has the right to use | CSV inbox (`docs/M2_OPERATIONS.md`) | whatever is supplied | none: local files | operator's responsibility; `display_cleared` needs recorded evidence | **Working route** |

## Coverage by data category
| Need | Best candidate | Zero-cost and permitted today? |
|---|---|---|
| Prices (end-of-day or delayed) | exchange files / vendor | **No**: needs a licence or written permission |
| Distributions | exchange corporate actions, issuer notices | **No** (exchange text); issuer notices need per-issuer permission |
| Distribution components | issuer disclosures (NDCF statements, intimations) | **Unknown**: per-issuer permission; transcription by the operator is possible |
| NAV (REIT/InvIT) | issuer valuation filings | **Unknown** (per issuer) |
| NAV (ETF) | AMFI file / AMC | **No** (AMFI terms) / unknown per AMC |
| Fundamentals (occupancy, WALE, leverage) | issuer presentations | **Unknown**; manual extraction only |
| ETF holdings | AMC portfolio disclosures | **Unknown** per AMC; monthly cadence |
| Announcements | exchange filings, issuer sites | **No** (exchange); unknown per issuer |
| G-Sec benchmark | RBI | **Not established** |

## Gap and what unblocks it
The gap is rights, not technology: every candidate that is reachable and free either reports terms against automated collection or public
redistribution, or has terms I could not find. To close it, in order of effort: (1) ask the issuers/AMCs you care about for written
permission to transcribe and display their disclosures (draft questions: `docs/DATA_PERMISSION_REQUESTS.md`); (2) email SEBI for permission
to reproduce registry/universe information; (3) ask NSE Data & Analytics and BSE for a display licence quote; (4) ask AMFI for a written
agreement. Until one lands, load only data you have the right to use, through the inbox. The registry keeps provenance, grades, reconciliation,
freshness and discrepancy handling in place, so the first cleared source plugs into the existing pipeline; a second source gives the
primary/secondary cross-check.
