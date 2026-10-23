# Deployment procedure (not executed: nothing has been deployed, no domain bought, no account created)

Everything below was verified only up to the static build and the pre-publication gate. Host-side steps are written from vendor documentation
summaries and are **untested**. Evidence labels: [S] search-reported, [A] assumption.

## 0. Preconditions (all must be true before a genuine launch)
1. At least one source is **CLEARED** and **display-cleared** in `config/sources.json`, with `clearance_evidence`, `display_evidence` and `terms_checked_on` filled from a written permission (see `docs/DATA_PERMISSION_REQUESTS.md`). Until then a public build shows identities, freshness and "withheld" only.
2. Legal review done (licensing, SEBI research/advice position, disclaimers, DPDP; checklist in `PHASE2_FEASIBILITY_REPORT.md` section 6). No ranking, tax or recommendation features exist.
3. `config/market_calendar.json` verified from the official NSE/BSE circulars (`status: verified_official` per date with `evidence_url`, `checked_on`, and the circular marked `read: true`; `holidays_complete: true`; pending exceptional sessions resolved). The loader refuses a "verified" claim without that evidence.
4. You own a domain and a hosting account (I cannot create either).

## 1. Build and gate (works today)
```
python3 -m venv .venv && .venv/bin/pip install .            # or: tools/verify_clean_install.sh  (does this in a temp dir and checks it all)
.venv/bin/python -m irie.cli run-cycle  --db irie.sqlite --registry config/sources.json --calendar config/market_calendar.json --inbox inbox
.venv/bin/python -m irie.cli build-site --db irie.sqlite --registry config/sources.json --calendar config/market_calendar.json --out dist --mode public
.venv/bin/python -m irie.cli check-site --dir dist           # MUST print "0 error(s)"; any error blocks upload
```
`check-site` verifies: required files; strict CSP meta + `_headers` (HSTS, nosniff, referrer policy, frame-ancestors none); no external URLs, `eval`, `innerHTML`, inline handlers;
`data.json` is public-mode and every shown value is OK, attributed, free of blocking flags and from display-cleared sources only (also price/NAV, history, holdings, news, links); no secrets, no local paths.
The build is byte-for-byte repeatable for the same inputs and clock (tested).

## 2. Upload `dist/` (five files: `index.html app.js style.css data.json _headers`)
**Option A, Cloudflare Pages (recommended: honours `_headers`) [A].**
1. Create a Pages project with **Direct Upload** and upload `dist/` (no Git integration needed, so no build runs and the 500-builds/month limit does not apply [S: [Cloudflare limits](https://developers.cloudflare.com/pages/platform/limits)]; 20,000 files and 25 MiB per file are far above our five files).
2. Custom domains > add your domain. If the domain's DNS is on Cloudflare the CNAME is created for you; otherwise add a CNAME to `<project>.pages.dev` at your registrar.
3. Wait for the certificate to issue; enable "Always use HTTPS". Confirm `_headers` took effect: `curl -sI https://your.domain/ | grep -i -E "strict-transport|content-security|x-frame"`.
**Option B, GitHub Pages.** Possible, but response headers cannot be set (only the CSP `<meta>` applies, no HSTS header) and GitHub's terms say Pages is not intended as free hosting for online businesses, e-commerce or SaaS [S: [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)]: a data product with a commercial angle should check that. Limits: 1 GB site, 100 GB/month soft bandwidth, 10 builds/hour soft (not for custom Actions workflows) [S].
4. Post-launch checks: open the site, confirm the SYNTHETIC notice is absent, the source table shows real sources, `curl https://your.domain/data.json | python -m json.tool` parses, and run `irie check-site` against a fresh download of the live files (`wget` the five files into a folder).

Domain cost: `.in` was reported around ₹625 (about $7) a year at one registrar, about $6 at another [T: [Domain India](https://www.domainindia.com/login/announcements/52), [Spaceship](https://www.spaceship.com/domains/cctld/in/)]; check the registrar's live price.

## 3. How the scheduled refresh runs at zero cost
Requirements: (a) the data store and inbox must stay **private** (they hold data this public repository may never hold); (b) runs must occur only in sessions plus one daily check; (c) state must persist between runs.
- **Recommended:** a **private** repository (an "ops" repo) holding only `config/`, the private inbox, and a copy of `.github/workflows/refresh.yml` with `IRIE_REFRESH_ENABLED=true`; it installs this code (`pip install git+https://github.com/<you>/Darvas`) and runs the three commands in section 1.
  The workflow is designed to fire about 8 times a day: hourly ticks 03:50-09:50 UTC on weekdays (09:20-15:20 IST) and one daily tick at 13:35 UTC (19:05 IST); the scheduler declines holidays, weekends and out-of-session times itself.
  Free-tier fit: standard GitHub-hosted runners are free for public repositories and self-hosted runners are free; private repositories on the Free plan get 2,000 minutes a month [S: [GitHub billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)]. At roughly 8 runs x 22 trading days x ~2 minutes this is about 350 minutes [A, my estimate], inside the allowance. The cache that holds `irie.sqlite` is best-effort; if it is evicted the next run rebuilds from the inbox files (the inbox, not the cache, is the source of truth).
  Publishing: add a final step that uploads `dist/` to the host with a deploy credential stored as a repository *secret* of the private repo (never committed). I did not add that step: it needs your account and authorisation.
- **Limits to plan for:** GitHub disables scheduled workflows after 60 days of no repository activity [S: [GitHub docs](https://docs.github.com/en/enterprise-server@3.20/actions/using-workflows/disabling-and-enabling-a-workflow)]; scheduled runs can start late [A], which the scheduler tolerates (it works from state, not from the exact tick). A missed tick shows up as a STALE source on the dashboard.
- **Alternative:** any machine you control (a home server or a free-tier VM [not researched]) running `irie run-cycle --loop --interval 900` under systemd (unit in `docs/M2_OPERATIONS.md`), which keeps the SQLite file on local disk.
- **Monitoring at zero cost:** the dashboard's own freshness table plus an external uptime check; a free monitor with 50 monitors at 5-minute intervals was reported [S: [UptimeRobot](https://uptimerobot.com/pricing.md)] (check its terms for commercial use).

## 4. Rollback
Re-upload the previous `dist/` (keep each release folder, named by `generated_at`). Withdrawing a source's permission: set `display_cleared: false` in the registry, rebuild, run `check-site`, upload; the values disappear from the next build.
