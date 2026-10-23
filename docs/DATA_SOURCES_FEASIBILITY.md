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

---
# M4 addendum: issuer, AMC and official-dataset assessment (searches 23-Oct-2026)

Same evidence labels: [S] reported in a search summary of the cited page (not read in full), [T] third-party commentary, [A] my assumption.
Nothing was scraped, subscribed to, or deployed; no permission is claimed.

| Candidate | Fields and instruments | Access / automation | History and frequency | Storage, derived calculations, display, CSV export | Fees | Evidence | Verdict |
|---|---|---|---|---|---|---|---|
| **REIT/InvIT issuer websites** (e.g. an InvIT's investor pages) | distributions, NDCF statements, results, NAV/valuation, leverage, presentations for that trust only | PDFs/pages on the trust's site; the same filings go to the exchanges | filings are periodic; SEBI sets quarterly results within 45 days and annual within 60 [S: [Saraf Partners](https://sarafpartners.com/?p=30813)]; NDCF statement with each distribution [S: [KSandK](https://ksandk.com/newsletter/sebi-guidelines-on-invit-and-reit/)] | One InvIT's disclaimer lets viewers download/print for viewing, reading or reference only and bars copying, modifying or distributing website material [S: [IndiGrid disclaimer](https://www.indigrid.co.in/disclaimer-policy)]. Offer documents hosted by banks bar copying or redistribution [S: [J.P. Morgan notice](https://indiaipo.jpmorgan.com/content/dam/jpm/india-private-limited/documents/embassy-office-parks-notice-to-investors-disclaimer.pdf)]. A REIT's own site terms were not found. | none | as cited | **Not permitted as published (one clear example); permission must be requested per issuer.** Strongest long-term route because issuers want their disclosures distributed. |
| **AMC / ETF issuer websites** | ETF NAV, factsheets, portfolio holdings, expense data for that AMC's funds | pages and downloadable spreadsheets; AMC portfolio disclosure is monthly or half-yearly [S: [SEBI circular](https://www.sebi.gov.in/sebi_data/attachdocs/jun-2018/1528207366367.pdf)] | monthly/half-yearly holdings; daily NAV | Six AMC sites reviewed share a pattern: personal viewing/download tolerated, copying/aggregating/redistribution or commercial reuse needs prior written consent [S: [Mirae](https://www.miraeassetmf.co.in/terms-of-use), [ICICI Pru](https://arch.icicipruamc.com:443/docs/default-source/default-document-library/terms-of-use.pdf?sfvrsn=2), [Jio BlackRock](https://www.jioblackrockamc.com/terms-and-conditions), [PPFAS](https://amc.ppfas.com/other-links/disclaimer.php), [Edelweiss](https://www.edelweissmf.com/terms-of-use), [IFCA](https://www.ifcamc.org/terms)] | none | as cited | **Not permitted without written consent; request per AMC.** |
| **SEBI website** | registered REIT/InvIT/MF lists, regulations | pages/PDFs | as published | reproduction free of charge after permission e-mailed to SEBI, with accuracy and credit; third-party material excluded [S: [SEBI website policy](https://www.sebi.gov.in/website-policy.html)] | none | as cited | **Permission route exists; not requested.** Covers universe/regulatory facts only, not prices or distributions. |
| **Official open datasets (data.gov.in, GODL-India)** | none relevant found | portal | per dataset | **This is the only genuinely open licence found**: worldwide, royalty-free, non-exclusive right to use, adapt and publish, commercially and non-commercially, with attribution (provider, source, licence, URL); versions differ by portal; third-party copyright excluded [S: [GODL-India](https://smartcities.data.gov.in/government-open-data-license-india), [data.gov.in terms](https://www.data.gov.in/terms-of-use)] | none | as cited | **Usable if a relevant dataset exists; my searches found no REIT/InvIT/ETF price, distribution or NAV dataset on it.** Re-check the catalogue; each dataset's own licence field governs. |
| **NSE free downloads (bhavcopy etc.)** | end-of-day prices | file download | daily; history from at least 2020 per a third-party package [T] | no NSE statement on redistribution or commercial reuse found; NSE Terms of Use report written permission needed [S] | none stated | [T: [nser package](https://cloud.r-project.org/web/packages/nser/index.html)] | **Blocked**: availability without a fee is not permission. |
| **Exchange filings for results/XBRL** | issuer financials | exchange websites | quarterly | exchange terms apply (see main table) | none | as in main table | **Blocked** pending exchange permission |
| **Facts vs compilations (legal note)** | n/a | n/a | n/a | Indian courts reportedly deny copyright in bare facts and public records but protect original editorial selection/arrangement [T: [Eastern Book Company v. Modak summaries](https://thelegalquorum.com/case-summary-eastern-book-company-ors-v-d-b-madak-anr/)]. That does **not** override contractual website terms. Whether our own derived calculations are free of the owners' terms is a question for counsel. | n/a | secondary summaries only | **Counsel question**, not a basis for scraping |

**Result:** no source was established that permits automated storage, derived calculation, public display and CSV export at zero fee. The only
open licence found (GODL-India) has no relevant dataset. Two permission routes cost nothing but a request: SEBI (universe/regulatory facts) and each
issuer/AMC (their own disclosures, which they are required to publish anyway). The existing safe fallback stays: operator-supplied files, `display_cleared = False`
by default, uncleared sources never fetched.

**Precise gap:** written permission, for each of (a) automated retrieval, (b) storage and history, (c) derived metrics, (d) public display and (e) CSV export, from at
least one source per data category in the coverage table above, or a GODL-licensed dataset that covers it.
