# 07 · Build plan

Work top to bottom. Each task has acceptance criteria; a task is done when they pass, with tests where marked. Convert each phase into GitHub issues before starting it (`to-spec`).

---

## Phase 0: Foundation (safety and correctness)

Nothing else starts until Phase 0's exit condition is met.

**T0.1 Deployment matches repo.** Confirm the Cloud Run services serve the current `main` (frontend and backend). Fix the deploy pipeline if not. Capture Cloud Scheduler jobs as code in the repo.
- AC: a visible build identifier (commit SHA) in the app footer and `/health` matches `main`; scheduler config committed.

**T0.2 Checks before building on assumptions.** Verify and record results in `01-current-state.md`:
- Twelve Data free tier returns LSE ETFs (daily and 1h) for 5 tickers from the universe.
- T212 API supports fractional quantities for those tickers (metadata precision).
- Whether any source gives live bid/ask for LSE ETFs (for the optional spread check).
- The four **(verify)** defects in `01-current-state.md`.
- AC: written results; build plan adjusted if Twelve Data lacks LSE (Yahoo primary for LSE).

**T0.3 Units and calendars.** GBP normalisation at the data boundary with stored units; exchange calendar for LSE/NYSE; trading-day and trading-hour arithmetic helpers.
- AC: tests for GBp→GBP, holiday/weekend counting, early closes. Invariants 8, 9.

**T0.4 Loom lots and exit levels.** Each fill creates a lot in the strategy's Book with `target_price`, `stop_price`, `exit_by`, fill price, quantity. Strategies can update `target_price` on their own lots only.
- AC: migration; invariant 7 test.

**T0.5 Exit enforcer.** Scheduled job per `05-data-and-execution.md`: T212 `currentPrice`, market hours, target/stop/time, idempotent sells of exactly the lot quantity, runs while Paused, not while Halted.
- AC: tests with a fake broker for each exit type; invariants 2, 3; runs on schedule in demo.

**T0.6 Budget fence.** Loom budget setting, Loom value/cash ledger, spendable cash, Manual-book exclusion, sell-quantity validation.
- AC: invariants 3, 4, 5; a test where the ISA holds the same instrument personally and Loom never trades it.

**T0.7 Sizing rewrite.** Sleeves, slots, per-trade from Loom value, check order, skip-with-reason log, deepest-dip ranking, fresh price at submission, quantity precision.
- AC: two signals in one pass never double-spend (invariant 5); skip reasons recorded; tests for each check.

**T0.8 Instrument groups.** Correlation grouping job, group cap across strategies, one-per-group per strategy, manual overrides.
- AC: invariant 6; VUSA/CSP1/VUAG land in one group on real data.

**T0.9 Pause and Halt.** Replace kill switch semantics with Pause (entries blocked) and Halt (all orders blocked); DB events with reason; checked before every submission. Daily loss limit and budget kill switch → Pause. Live valuation from T212 prices. Snapshot poisoning fix (previous close as baseline; >30% implied move = data error alert, no pause).
- AC: invariants 1, 2; tests for automatic pause triggers and for the poisoning scenario in BACKLOG.

**T0.10 Notifications live.** SMTP and VAPID configured via Cloud Run secrets; real `notify_email`; "Send test" endpoints; immediate alerts for approvals, pause/halt, failed orders, missed runs.
- AC: Aayan receives a test email and push on his phone; approve link works from the email.

**T0.11 Dead-man's switch.** Every job pings a heartbeat on success; missed ping emails Aayan.
- AC: disabling a job for one interval produces an alert.

**T0.12 Hide backtest.** Remove Backtest nav/page; keep backend code but unexposed.

**Phase 0 exit condition:** one full demo trading day with a hand-seeded test position that exits correctly on target, on stop and on time (three positions); no duplicate orders; fence holds; notifications and heartbeats arrive.

---

## Phase 1: Strategies into demo

**T1.1 Engine timeframes.** Strategies declare `daily` or `hourly`; scheduler runs pre-open daily scans (LSE, NYSE) and hourly LSE scans per `05-data-and-execution.md`. Previous-close rule for daily indicators.
- AC: a daily strategy produces identical signals whether the hourly scan runs or not.

**T1.2 Market regime.** UK equal-weight index and SPY regime computed daily; exposed via endpoint.

**T1.3 Universe builder.** Weekly job per `05-data-and-execution.md`; versioned snapshots; report differences vs the initial list in `03-strategy-specs.md`.

**T1.4 Retire old strategies.** Remove Low-Vol Compounder (old), Volatility Harvester, Trend Follower from the registry; keep code history in git. Fix registry keying if T0.2 confirms the defect.

**T1.5 Deep Dip.** Per spec, including daily target refresh and structured "why it fired" values.

**T1.6 Compounder.** Per spec: hourly z on 40 bars, daily filters, fixed target, 45 trading hours, signal expiry at end of next bar.

**T1.7 Crash-buyer.** Rework `value_quality_dip_buyer.py` per spec: ETFs with UK regime below 200-day; US stocks with SPY filter, fundamentals gate, stock cap.

**T1.8 Squeeze Breakout in Shadow.** Existing logic, exits per spec, shadow mode (no orders, would-be outcomes recorded).

**T1.9 Shadow mode and shadow configs.** Strategy status Off/Shadow/Active; alternative config versions tracked in parallel without orders.

**T1.10 Typed parameters.** Replace JSON params with a typed schema per strategy (name, unit, default, range, meaning, raising-means text) served to the UI. Config version creation validates bounds.

**Parallel research (outside Claude Code):** re-run Deep Dip on real open prices and on the full universe; results into `08-research-log.md`; adjust Deep Dip only if results differ materially.

**Phase 1 exit condition:** all four strategies generating signals in demo for 5 trading days; each signal's "why it fired" values match an independent recomputation on a sample of 10 signals.

---

## Phase 2: Demo tracking + UI rebuild

**T2.1 UI rebuild** per `06-ui-spec.md` build order (components → shell → Approvals → Overview → Strategies → History → Settings → Insights).

**T2.2 Research vs reality.** Store research baselines per config version (values from `08-research-log.md`); compute actuals from closed demo trades; verdict logic with gate counts.

**T2.3 Fee and fill reconciliation** from T212 transaction history.

**T2.4 Time-exit follow-up tracking.**

**T2.5 Daily summary** (email/push at 17:00 + archive in Insights): Loom value, trades opened/closed, P/L, skipped signals with reasons, time exits and follow-ups, upcoming exits.

**T2.6 Instrument page.**

**T2.7 Settings** (nine sections) and settings audit log.

**T2.8 Health endpoint** for the header dot (job heartbeats, source status, Twelve Data usage).

**Operational checkpoint (week 4):** no missed exits, no duplicate orders, no fence breaches, no silent missed runs.

**Approval progression:** Manual for the first ~10 trades per strategy; then Auto for the Compounder.

**Phase 2 exit condition:** per-strategy promotion gates in `LAUNCH-TIMELINE.md`.

---

## Phase 3: Live with £1,000 (Aayan's decision, not Claude Code's)

Claude Code does not enable live trading. When Aayan enables it: first two weeks Manual approval for every strategy; promotion is per strategy.

---

## Phase 4: Scale

- **T4.1 Capital lending** (prototype first).
- **T4.2 More slots** as the budget grows (Settings only).
- **T4.3 Two-step scan** if the universe exceeds the Twelve Data budget.
- **Research backlog:** intraday entry timing for Deep Dip; VIX as a Crash-buyer input; economic-calendar filter; wider ETF universe; Squeeze sample size.
