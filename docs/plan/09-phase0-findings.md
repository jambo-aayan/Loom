# 09 · Phase 0 findings: T0.1 and T0.2

Checked on 22 Sep 2026 by Claude Code against `main` at `76770a6`. This is the first pass at Phase 0, done **before any code change**. It records what the repo and the live services actually show, and where that differs from `01-current-state.md`, `05-data-and-execution.md` and `07-build-plan.md`.

It is written for the planning chat that produced `docs/plan/`, so the plan can be updated. Each finding says how it was checked. **Proposed plan changes** and **Open questions** are at the end.

Access limits during this check: no GCP access (so Cloud Run and Cloud Scheduler could not be read directly), no Trading 212 access (the sandbox proxy blocks `demo.trading212.com` and no key was available), and no Twelve Data key (only the public `demo` key and the free reference endpoints). GitHub Actions and Vercel were readable.

---

## Summary

| # | Finding | Effect on plan |
|---|---|---|
| 1 | **Twelve Data's free tier does not cover LSE ETFs.** All 5 tested ETFs need the paid "Grow" plan. | Big. Yahoo must become the main LSE source, or Twelve Data must be paid for. Affects `05`, the hourly Compounder and the Twelve Data call budget. |
| 2 | The code passes Yahoo-style tickers (`VUSA.L`) to Twelve Data, which doesn't accept that format. LSE data has most likely been coming from the yfinance fallback all along. | Confirms 1 in practice. The research results (Yahoo data) and the live data source may already match. |
| 3 | Twelve Data returns some LSE ETFs in pence (GBp) and others in pounds (GBP). | Supports T0.3 (convert to GBP as data comes in). No change. |
| 4 | Frontend and backend both serve the latest `main` (`76770a6`). No deploy gap. | T0.1 is mostly done. Only the visible build ID is missing. |
| 5 | The frontend is on **Vercel**, not Cloud Run. | Fix the wording in T0.1 and `01`. |
| 6 | The kill switch UI **is** deployed and in the nav (Settings → "Kill switch (demo)"). | The "deploy gap" explanation in `01` is wrong. The reason Aayan can't see it is still unknown. |
| 7 | The Cloud Scheduler setup is partly in the repo (`infra/gcp/setup.sh`), times are in UTC, and it probably no longer matches what's live. | T0.1 needs the live job list from Aayan. Time zone handling is needed. |
| 8 | Backtest fills at the signal-day close: **confirmed**. | Already parked (D4). No change. |
| 9 | Time exits count calendar days: **confirmed** (backtest only; there is no live time-exit code). | No change; T0.3/T0.5 cover it. |
| 10 | Twelve Data `outputsize` bug: **not reproduced**. | Remove from `01`. |
| 11 | Strategy registry keying: **not a defect today**. | Downgrade in `01` and T1.4. |
| 12 | T212 fractional quantities and a live bid/ask source: **not checked** (no access). | Still open. |

---

## T0.1: does the deployment match the repo?

### Hosting (differs from plan)

`01-current-state.md` says "Hosting: Google Cloud Run" and T0.1 says "Confirm the Cloud Run services serve the current `main` (frontend and backend)". According to `docs/deployment.md` and the live services, the actual setup is:

| Part | Where | How it deploys |
|---|---|---|
| Frontend (Next.js) | **Vercel**, project `loom` | Vercel's git integration, on every push to `main` |
| Backend API | Cloud Run service `loom-api`, `europe-west2` | GitHub Actions `deploy-backend.yml`, on pushes to `main` that touch `backend/**`: tests → image build → `alembic upgrade head` → deploy |
| Scheduled jobs | Cloud Run Jobs `loom-trade-pass`, `loom-screen-insights`, `loom-research-insights`, `loom-reconcile`, started by Cloud Scheduler | Same workflow updates each job to the new image |
| Database | Neon Postgres | Migrations run from CI |

### What's deployed

- `origin/main` HEAD: `76770a64` ("Fall back to gemini-3.5-flash-lite…", 11 Sep 2026).
- Backend: GitHub Actions run #26 for `76770a64` finished **success**. It deployed both the Cloud Run service and all four jobs.
- Frontend: the latest Vercel **production** deployment is `76770a64`, state READY.
- **Conclusion: both halves serve the current `main`.**

Caveat: the backend workflow only runs when `backend/**` changes. A commit that only touches the frontend or docs won't redeploy the backend. That's correct behaviour, but it means "backend SHA = main SHA" won't always hold exactly. The build ID check should compare the backend SHA with the last commit that touched `backend/`.

### The kill switch "deploy gap" is not real

`01` says the kill switch UI "exists in `frontend/app/settings/page.tsx`… Aayan does not see it in the deployed app. Suspected deploy gap."

- The kill switch card is in `frontend/app/settings/page.tsx` (label "Kill switch (demo)", line 116). It is rendered every time; it isn't hidden behind a flag.
- `/settings` is in the nav (`frontend/components/NavShell.tsx:17`).
- The file last changed on 7 Sep 2026 (`f17ab4b`), well before the deployed commit.
- So it **is** in the deployed app. Possible explanations, none confirmed: (a) Aayan looked on a different page; (b) the Settings page shows a load error (all four API calls sit in one `Promise.all`, so if any one fails the page shows an error message, but the kill switch card still renders with its default state); (c) the phone is showing an old version cached by the PWA service worker.
- **The "hardcoded to `demo`" part is accurate.**

### Build identifier (not built yet)

- Backend `/health` (`backend/loom/api/main.py:60`) returns only `{"status": "ok"}`.
- The frontend shows no commit SHA.
- Straightforward to add: pass the SHA into the Docker image as a build argument in `deploy-backend.yml` and return it from `/health`; the frontend can use Vercel's `VERCEL_GIT_COMMIT_SHA`.

### Cloud Scheduler (partly in the repo already)

`01` says scheduling is "Not in the repo". Actually, `infra/gcp/setup.sh` (lines 184–211) creates or updates these jobs:

| Job | Cron | Time zone |
|---|---|---|
| `loom-trade-pass` | `0 8 * * 1-5` | not set → UTC (09:00 UK in summer) |
| `loom-screen-insights` | `15 8 * * 1-5` | UTC |
| `loom-research-insights` | `30 8 * * 1-5` | UTC |
| `loom-reconcile` | `0 18 * * 1-5` | UTC |

- The planning notes say trade-pass was later changed by hand to every 30 minutes. If so, the live jobs no longer match `setup.sh`. **This could not be checked without GCP access.**
- None of the jobs set `--time-zone`. The target schedule in `05` is written in UK time, and 5-minute exit enforcer runs during LSE and NYSE hours need correct UK/US daylight-saving handling. Scheduler jobs should set `--time-zone=Europe/London`, and the job itself should check the exchange calendar (a cron can't know about bank holidays).
- **Needed from Aayan:** output of `gcloud scheduler jobs list --location europe-west2` (and `describe` for each job), so the live state can be captured as code.

---

## T0.2: checks before building

### Twelve Data and LSE ETFs: free tier does NOT cover them

Checked with Twelve Data's public reference endpoint `GET /etf?symbol=<X>&show_plan=true`, looking only at the LSE listing:

| Ticker | LSE currency | Plan needed |
|---|---|---|
| VUSA | GBP | Grow (paid) |
| CSP1 | **GBp** | Grow |
| VUAG | GBP | Grow |
| ISF | **GBp** | Grow |
| VWRL | GBP | Grow |

- The free plan is "Basic". Every LSE listing tested needs "Grow" (individual) or "Venture" (business).
- The same tickers also exist on Munich/XETRA in EUR. An unqualified symbol like `VUSA` may resolve to a **European listing in EUR**. Symbols must always name the exchange (`VUSA:LSE` or `exchange=LSE`), and the currency must be checked on every response.
- Twelve Data's own currency codes differ between ETFs (GBP vs GBp). Whether that matches the real quoting unit per instrument still needs checking against T212 metadata.
- An actual price request (`time_series`) for an LSE symbol couldn't be tested: the `demo` key only allows a few US symbols. A free key would confirm whether a plan-restricted symbol returns an error or nothing.

### The code already bypasses Twelve Data for LSE (probably)

- The default universe is `["VUSA.L", "VWRL.L", "TSLA", "NVDA"]` (`backend/loom/cli/main.py:63,110`), in Yahoo format.
- `TwelveDataSource.get_history` (`backend/loom/market_data/twelve_data.py`) passes the ticker straight through as `symbol`, with no exchange mapping. Twelve Data doesn't use the `.L` suffix.
- `PrimaryWithBackfillSource` (`market_data/composite.py`) falls back to yfinance. So **LSE bars in production most likely come from Yahoo already**, while US bars (TSLA, NVDA) come from Twelve Data. This should be confirmed from Cloud Run logs.
- There's no exchange/symbol mapping layer anywhere. That's a missing piece for the universe builder (T1.3).

### Twelve Data `outputsize` (verify item): not reproduced

- `GET /time_series?symbol=AAPL&interval=1day&start_date=2020-01-01&end_date=2026-09-01&order=ASC` with the demo key returned **1,674 bars** starting 2020-01-02. That's the whole range, not the default 30.
- With `start_date`/`end_date` set, Twelve Data returns up to its 5,000-point maximum. Loom's lookbacks are far below that for daily bars. For **hourly** bars, 5,000 points ≈ 555 LSE trading days, still enough for 40-bar and 250-day windows.
- **Recommendation:** remove this defect from `01`. Keep in mind that one request is capped at 5,000 points.

### T212 fractional quantities: NOT checked

- The sandbox proxy blocked `demo.trading212.com` (CONNECT 403), and no T212 key is available here.
- To check: `GET /api/v0/equity/metadata/instruments` with the demo key. Look at the entries for VUSA, CSP1, VUAG, ISF and VWRL (`ticker`, `type`, `currencyCode`, `maxOpenQuantity`, and any fields about precision or fractional trading). Aayan can run this, or the demo key can be added to the Claude Code environment.

### Live bid/ask for LSE ETFs: NOT resolved

- T212: no general quote endpoint (as `05` says); positions only give `currentPrice`.
- Twelve Data: LSE is behind a paid plan (above), and bid/ask is a separate question on top of that.
- Yahoo: rate-limited the sandbox (HTTP 429). Yahoo's `quote` data sometimes includes bid/ask for `.L` tickers, but it's unofficial and often empty outside market hours.
- **Recommendation:** assume no reliable free bid/ask source. Keep the spread check optional/off, and measure real spread from T212 fill prices against the reference price (fee and fill reconciliation, T2.3).

### The four "(verify)" defects in `01-current-state.md`

| Defect | Verdict | Evidence |
|---|---|---|
| Backtest fills at signal-day close | **Confirmed** | `backtest/engine.py:196` (sell), `:208`, `:212` (buy: `entry_price=bar.close` on the signal date `d`). Exits also check against `bar.close` (`:181–184`). |
| Time exits in calendar days | **Confirmed** | `backtest/engine.py:127`: `held = (current_date - date.fromisoformat(trade.entry_date)).days`. `trade_reconstruction.py:37` measures hold length in calendar days too. Strategy params are all `time_exit_days`. There is no live-trading code that enforces time exits at all (matches "Missing: exit enforcement"). |
| Twelve Data outputsize bug | **Not reproduced** | See above. |
| Strategy registry keying | **Not a defect now** | `trading_pass.py:45`: `STRATEGY_REGISTRY[cls.key] = cls`. The lookup at `:223` uses `strategy_row.key`. Both use the strategy class key. It would only matter if one strategy class had several DB rows (per-strategy configs): each row resolves to the same class, and parameters come from that row's promoted config version, which is already per row. Nothing is broken today; look at it again when shadow configs arrive (T1.9). |

### Other things noticed

- Only ADRs **0001–0016** exist on `main`. The 0017–0023 mentioned in `01` don't exist, so nothing extra to reconcile.
- Backtest is still in the nav (`frontend/components/NavShell.tsx:11`); that's T0.12, as expected.
- `/health` has no dependency checks (DB, broker, data source). That's fine for T0.1; T2.8 extends it.

---

## Proposed plan changes

For the planning chat to accept, change or reject.

1. **Data sources (`05`, `02`, ADR-0008):** make **Yahoo the main source for LSE bars (daily and hourly)**, with Twelve Data the main source for US stocks. Or decide to pay for Twelve Data Grow. Consequences:
   - The Twelve Data budget line in `05` ("~350–380 calls/day for hourly LSE scans") no longer applies. Hourly LSE load moves to Yahoo, which has no published limit but does rate-limit.
   - Yahoo being "never the only source for a live decision without a staleness check" (`05`) now covers every LSE entry. Staleness checks and the >50% price-difference guard become more important.
   - Research used Yahoo 60-minute bars, so live and research data would come from the same source. That's a plus.
   - The "two-step scan" (T4.3) was about the Twelve Data budget; decide whether it's still needed.
2. **Add a symbol mapping layer** (T0.3 or T1.3): one Loom instrument ID mapped to the T212 ticker, the Yahoo ticker (`VUSA.L`) and the Twelve Data symbol (`VUSA:LSE`), plus currency and unit. Never send an unqualified symbol to a data source.
3. **Reword T0.1:** "Vercel frontend and Cloud Run backend serve the current `main`". The backend build ID should match the last commit that touched `backend/`.
4. **Scheduler:** capture the live jobs as code, set `Europe/London` on all jobs, and have each job check the exchange calendar itself.
5. **Update `01`:** remove the outputsize defect; downgrade registry keying; replace "suspected deploy gap" for the kill switch with "deployed; reason not visible is unknown"; replace "Scheduling: not in the repo" with "partly in `infra/gcp/setup.sh`; live state may differ".
6. **Spread check:** plan for it to be unavailable; measure real spreads from fills instead.

## Open questions

1. **Pay for Twelve Data Grow, or use Yahoo as the main LSE source?** (Recommended: Yahoo, since the research was built on it. Decide before T0.3 and T1.1.)
2. **What are the live Cloud Scheduler jobs?** Aayan to paste `gcloud scheduler jobs list --location europe-west2`.
3. **T212 metadata for the five ETFs:** fractional support, quantity precision and currency. Aayan to run the metadata call, or add the demo key to the Claude Code environment.
4. **Where did Aayan look for the kill switch, and on which device?** Checks for a cached PWA version or a Settings page error.
5. Should Claude Code go ahead now with the parts of T0.1 that don't depend on these answers (the build SHA in `/health` and in the footer)?
