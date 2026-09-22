# 01 · Current state

Verified by reading the repo snapshot (`Loom-main`, Sep 2026). The four items an earlier audit marked **(verify)** were checked on 22 Sep 2026 against `main` at `76770a6`; results are inline below, with evidence in `09-phase0-findings.md`.

Note: `main` contains ADRs 0001–0016 only. The ADRs up to 0023 mentioned in an earlier briefing do not exist.

## Architecture

| Layer | What's there |
|---|---|
| Frontend | Next.js 14 + Tailwind, `frontend/app/*`. Pages: overview, approvals, strategies (+ detail), backtest, insights, performance, history, settings. ~1,400 lines total. Only two components (`NavShell`, `RegisterServiceWorker`). PWA manifest + service worker. |
| Backend | FastAPI, `backend/loom/`. SQLAlchemy models. Routers: signals, strategies (+ config versions, draft backtest), trading (kill switch, gates, run), portfolio (books), performance (+ correlation), insights (screen, research, ask, digest, position commentary), push, action-links, settings. |
| CLI | `loom backtest`, `loom trade-pass`, `loom screen-insights`, `loom research-insights`, `loom reconcile` (`backend/loom/cli/main.py`). |
| Hosting | Frontend on **Vercel** (git integration, deploys every push to `main`). Backend API on **Cloud Run** service `loom-api` (`europe-west2`), deployed by GitHub Actions `deploy-backend.yml` on pushes to `main` that touch `backend/**`. Scheduled jobs are Cloud Run Jobs on the same image. Database on Neon. On 22 Sep 2026 both frontend and backend served `main` at `76770a6`. |
| Scheduling | **Partly in the repo:** `infra/gcp/setup.sh` creates four Cloud Scheduler jobs (trade-pass 08:00, screen-insights 08:15, research-insights 08:30, reconcile 18:00, weekdays) with no time zone set, so they run in UTC. Trade-pass was later changed by hand to every 30 minutes, so the live jobs likely differ from the script. Capture the live jobs as code (T0.1). |

## Built and working (in code)

- **Trading pass** (`trading_pass.py`): strategies → signals → approval → orders.
- **Approve / reject** signals (API + UI).
- **Duplicate-order protection**: idempotency key `signal-{id}` checked before submitting (`execute_signal`). ADR 0014.
- **Kill switch**: DB event log (`KillSwitchEvent`), per environment, checked immediately before every order. Engage/resume endpoints.
- **Live-trading gate** and **auto-trading gate**: global switches, DB-backed.
- **Reconciliation** (`reconciliation.py`): positions Loom didn't place are recorded in a `Manual` Book. Idempotent.
- **Books**: per-strategy attribution; FIFO trade reconstruction (`trade_reconstruction.py`).
- **Evaluation** (`evaluation.py`): drawdown, win rate, profit factor, expectancy, trade-level Sharpe/Sortino vs benchmark.
- **Correlation between Books** (`correlation.py`), weekly-bucketed.
- **Market data**: `PrimaryWithBackfillSource` = Twelve Data primary, yfinance fallback (`market_data/composite.py`). **No longer the target** for LSE: D25 makes Yahoo primary for LSE and Twelve Data primary for US only.
- **Fundamentals** from yfinance (`fundamentals.py`): P/E, dividend yield, debt/equity, sector. Missing values are treated as "skip", never defaulted. Correct.
- **Config versions**: draft → backtest → diff → promote; every version kept (`config_versions.py`, strategy detail page, JSON textarea).
- **Confidence calibration** module (`calibration.py`): buckets historical signals by strength. Needs trade history to be useful.
- **Insights** (`insight/`): screening note per signal; research tier (web search, thesis + key risks) gated to investment-style strategies; free Gemini auto pass; paid Claude manual pass; position commentary; free-form ask; digest endpoint. Advisory only by construction.
- **T212 client** reads `currentPrice` for held positions (`execution/t212_client.py`); used for P/L on the portfolio page.

## Built but not visible or not configured

- **Kill switch UI** exists in `frontend/app/settings/page.tsx` ("Kill switch (demo)"), **hardcoded to `"demo"`**. It **is** deployed and Settings is in the nav; there is no deploy gap. Why Aayan doesn't see it is unknown and won't be investigated: the header Pause/Halt in the UI rebuild replaces it (D33).
- **No build identifier.** `/health` returns only `{"status": "ok"}`; the frontend shows no commit SHA (T0.1).
- **Notifications** (`notifications/`): email via SMTP with signed one-tap approve/reject links; Web Push via VAPID. Both default to **Fake senders** because `settings.py` has empty `smtp_host`, empty VAPID keys and a placeholder `notify_email`. Almost certainly nothing has ever been delivered.

## Broken

| Defect | Where | Effect |
|---|---|---|
| **Stale cash in sizing** | `trading_pass.py` reads `account.cash` once per pass and reuses it; `risk.py` sizes `quantity = cash × position_cash_fraction / price` per signal | Two signals approved in one pass are both sized against the same unspent cash. Exposure checks do re-read positions; the cash check does not. |
| **Sizing from cash, not account value** | `risk.py` | Trade size shrinks as money is invested, so size depends on processing order. |
| **Stale reference price** | `Signal.reference_price` set at generation, used for quantity at approval time (BACKLOG) | £ spent drifts from intended when approval is later. |
| **Daily loss uses cost basis** | `daily_loss.py` | Blind to unrealised losses. |
| **Daily loss snapshot poisoning** | `daily_loss.py` (BACKLOG) | A bad first snapshot of the day (e.g. misconfigured credentials) causes repeated false kill-switch trips; only fix was deleting the DB row. |
| **Backtest fills at signal close** | `backtest/engine.py:196,208,212` (**confirmed**) | Overstates edge. Backtest is being hidden (decision D4), so this is parked, not fixed. |
| **Time exits in calendar days** | `backtest/engine.py:127`, `trade_reconstruction.py:37` (**confirmed**; backtest and hold-length only, since there is no live time-exit code) | Hold periods wrong around weekends/holidays. Fixed by trading-day helpers (T0.3) and the exit enforcer (T0.5). |

**Checked and not defects (22 Sep 2026):**
- *Twelve Data outputsize*: with `start_date`/`end_date` set, Twelve Data returns the whole range up to its 5,000-point cap (a 2020–2026 daily request returned 1,674 bars). Removed.
- *Strategy registry keying*: the registry is already keyed on the strategy class key (`trading_pass.py:45`) and looked up by the DB row's key (`:223`). Nothing broken today; revisit with shadow configs (T1.9).

**Data-source defects found 22 Sep 2026:**
- **Twelve Data's free tier doesn't cover LSE listings** (paid Grow plan needed). Decision D25: Yahoo becomes primary for LSE.
- **Unqualified symbols.** The default universe uses Yahoo-format tickers (`VUSA.L`, `cli/main.py:63,110`) and `TwelveDataSource` passes them unchanged, which Twelve Data doesn't recognise. LSE bars in production have most likely come from the yfinance fallback. There is no symbol mapping layer (T0.3).
- **Mixed units at source.** Twelve Data reports CSP1 and ISF in GBp and VUSA, VUAG and VWRL in GBP; nothing normalises this (T0.3).

## Missing

- **Exit enforcement.** No job, CLI command or code path checks open positions against exit plans. Only `low_vol_compounder` and `volatility_harvester` have any exit logic, and only inside their own signal generation. **Nothing currently protects open positions.**
- **Pass completion / health signal.** `notify_new_signals` only fires when there are pending approvals; a clean pass or a crashed pass produces nothing.
- **Budget fence.** No concept of a Loom budget; sizing uses the whole account.
- **Exclusion of personal holdings.** The Manual book is tracked but strategies can still buy the same instruments, and T212 merges positions.
- **Fee reconciliation.** Costs are modelled only; T212 transaction history (fees, FX) is never pulled.
- **Hourly strategy support** (Compounder), market-regime filter, instrument groups, sleeves/slots.
- **Exchange calendar and trading-day arithmetic.** No holidays, early closes or session hours anywhere (T0.3).
- **Frontend design.** The deployed UI is a functional scaffold; it does not implement the prototype or the v4 design.

## Strategies in code today

| File | Status under this plan |
|---|---|
| `low_vol_compounder.py` | **Retire.** Logic (calm + above 50-day, hold for drift) measured as no edge. The name "Compounder" is reused for a new, different strategy. |
| `volatility_harvester.py` | **Retire.** Nearest ancestor of Deep Dip; replace with the Deep Dip spec. |
| `trend_follower.py` | **Retire.** Negative in 9/9 years on the universe. |
| `volatility_breakout.py` | **Keep as Squeeze Breakout.** Entry and exits already match the spec; run in shadow. |
| `value_quality_dip_buyer.py` | **Rework into Crash-buyer** per spec (market filter, new exits). Fundamentals gate reused for US stocks. |
