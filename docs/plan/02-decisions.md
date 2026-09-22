# 02 · Decisions

Each decision: what, why, and what it replaces. Evidence references point to `08-research-log.md` (R-numbers).

## Product

**D1. Build broadly, prove in demo, promote on evidence.** Every strategy runs in T212 Demo first. Promotion to Live is per strategy, against the gates in `LAUNCH-TIMELINE.md`. Why: nothing has been tested with real fills yet; demo is free.

**D2. Loom is a personal tool with a fenced budget.** Loom trades only its own budget (£1,000 to start) inside Aayan's ISA and never touches his other holdings. Why: the ISA holds ~£6.5k of personal investments that must be unaffected.

**D3. Research happens outside the app.** New rules are tested in notebooks/chat against real data with the method in R0; the app implements proven rules and records live results. Why: fast iteration and statistical rigour without building research tooling into the product.

**D4. Hide the in-app backtest.** Remove the Backtest tab. Do not fix its known defects now. Why: it fills at signal close and overstates edge; an unreliable number on screen is worse than none. The demo track record is the forward test.

**D5. Multi-slot engine, not a daily batch.** Entry scans run hourly during market hours; each strategy declares its timeframe (daily or hourly). Daily strategies evaluate once, before the open, on the previous close. Supersedes ADR 0002 (scheduled single daily pass). Why: the Compounder needs hourly evaluation; daily strategies must still evaluate exactly as researched.

**D6. AI insights stay advisory.** Never an input to confidence, sizing, ranking or approval. Why: LLM narrative can't be measured or given a confidence interval; it's context for the human.

## Strategies

**D7. Roster: Deep Dip, Compounder, Crash-buyer, Squeeze Breakout.** Specs in `03-strategy-specs.md`. Supersedes ADR 0009's roster.

**D8. Retired and not to be rebuilt without new evidence:** Steady Dip, old Low-Vol Compounder logic, Trend Follower (R1), 12-month momentum rotation (R2), leveraged products (not available via T212 API/ISA), US single stocks in dip strategies (R12), looser Compounder trigger (R13), "never sell at a loss" exits (R5).

**D9. Market-regime filter on both dip strategies.** Instrument above its own 50-day average AND broad market above its 200-day average, measured on the previous daily close. Why: rescued Deep Dip (R1) and turned the Compounder from break-even into a clear edge (R4).

**D10. Crash-buyer uses the inverted filter.** Market below its 200-day average. Why: makes it hand off with the dip strategies; almost no cost (R7).

**D11. Universe for dip strategies: GBP-denominated LSE equity index and equity sector ETFs.** No gold, property, dividend-income funds or bonds. Currency read from metadata; USD lines on the LSE excluded. Why: removes FX fee and stamp duty; the market filter is about equities (R14).

**D12. Crash-buyer may trade US large caps** with a fundamentals gate and mandatory SPY-below-200-day filter, at a small allocation, as a demo experiment. Why: Aayan wants large-company exposure; the evidence is weak (R11), so it's treated as unproven.

**D13. Confidence scores are uncalibrated and not shown as probabilities.** When slots are full, rank by dip depth (most negative z first). Calibration can replace this once there is trade history.

## Exits

**D14. Exit levels are stored on the position at entry** (`target_price`, `stop_price`, `exit_by`). Strategies may refresh their own positions' targets on their scan; the exit enforcer only compares live prices to stored levels. Exception: Squeeze Breakout's volatility exit is issued by its daily pass.

**D15. Exit prices come from T212's held-position prices.** No market-data calls for exits. Market hours only. Market sell orders.

**D16. Exit rules per strategy** as in `03-strategy-specs.md`. Dip strategies: target = back to average, far catastrophe stop, time limit. Squeeze: real stop. Why: R5–R8.

**D17. Deep Dip target refreshes daily; Compounder target is fixed at entry.** Why: freezing Deep Dip's target cut efficiency by a third; for the Compounder the two were equivalent (R8, R9).

**D18. Keep time exits; track what happens after them.** After a time exit, record the price path for 20 trading days (Deep Dip) or 45 trading hours (Compounder) and show it in History. Why: extending holds didn't help on average (R10), but Aayan should be able to verify that on his own trades.

## Sizing, risk, safety

**D19. Size from the Loom budget's value, with sleeves and slots.** Per-trade = sleeve % × budget value ÷ slots. Skip when no slot is free; never shrink. Replaces cash-fraction sizing. Details in `04-sizing-and-risk.md`.

**D20. Instrument groups with caps across strategies.** Groups built automatically by correlation. One ticker per group per strategy. Why: the "diversified" ETF list is mostly a few indices repeated; overlap between strategies concentrates there (R11b).

**D21. Exclude instruments Aayan holds personally** from every strategy. Why: T212 merges positions; a Loom sell could sell his shares.

**D22. Pause vs Halt.** Header button pauses new trades (exits keep running). Halt everything (all orders, sells included) is manual, in Settings, behind confirmation. Daily loss limit and budget kill switch **pause**, never halt. Why: halting sells in a drawdown leaves positions unprotected.

**D23. Risk profile default: Balanced**, for demo and initially for live. Why: demo must run exactly as live will or its track record doesn't transfer.

**D24. Capital lending, later.** Dip strategies may borrow up to half of the dormant Crash-buyer sleeve; borrowed money is repaid first. Build after basic sizing is proven (Phase 4).

## Data

**D25. Data sources by market (revised 22 Sep 2026, see `09-phase0-findings.md`).** Yahoo is the primary source for **LSE** daily and hourly bars; Twelve Data is primary for **US stocks only**; Yahoo also supplies fundamentals; T212 supplies execution and held-position prices. Do not pay for Twelve Data Grow. Why: Twelve Data's free tier doesn't cover LSE listings (paid "Grow" plan needed), and the research used Yahoo bars, so live and research data match. Rules:
- Every data request uses an exchange-qualified symbol from the symbol mapping layer (T0.3); currency and unit are checked on every response. Normalise GBp/GBP at the boundary.
- No data or stale data for an instrument → no entries for it in that scan. Exits are unaffected (they use T212 prices, D15).
- The hourly scan runs a few minutes after the hour and checks that the latest bar is the bar that just closed before using it.
- Yahoo requests are batched, back off on HTTP 429, and the share of scans with fresh data is recorded (surfaced later in the health endpoint, T2.8).
Supersedes ADR 0008 for LSE instruments.

**D26. Hourly, not 30-minute, bars for the Compounder.** Why: matches the tested data (Yahoo 60-minute bars). Hourly LSE bars come from Yahoo (D25), so the Twelve Data call budget no longer limits the Compounder.

## Features

**D27. In scope:** research vs reality dashboard, shadow configs, live valuation from T212 prices, daily summary, instrument page, dead-man's switch, time-exit tracking, fee reconciliation, notifications configured with test buttons, one-tap approvals.

**D28. Out of scope for now:** news sentiment, AI as trading input, leveraged products, Telegram (later), VIX and economic calendar (research first), paid data (only when free tier is the bottleneck).

**D29. Settings spec** as in `06-ui-spec.md`: nine sections, all changes logged, strategy edits create versions, bounded fields.

**D30. UI reference is the v4 design.** The frontend is rebuilt on existing plumbing: shared components first, then Approvals and Overview.

## Operations (added 22 Sep 2026, from `09-phase0-findings.md`)

**D31. Scheduler as code, UK time, calendar-aware jobs.** The live Cloud Scheduler jobs are captured in the repo; every job uses time zone `Europe/London`; each job checks the exchange calendar itself and exits early on a non-trading day (cron can't know about bank holidays or early closes).

**D32. No spread check on the approval card for now.** No reliable free bid/ask source exists for LSE ETFs. Real spreads are measured from T212 fills in fee and fill reconciliation (T2.3).

**D33. Kill switch UI is not investigated further.** The header Pause/Halt in the UI rebuild (D22, `06-ui-spec.md`) replaces it.

## ADRs to write

| New ADR | Supersedes / relates to |
|---|---|
| Multi-slot hourly engine with per-strategy timeframe | Supersedes 0002 |
| Strategy roster v2 (four strategies, retired list) | Supersedes 0009 |
| Exit levels on positions + exit enforcer using T212 prices | New |
| Loom budget fence and personal-holdings exclusion | Relates to 0010 (Books) |
| Sizing: sleeves, slots, instrument groups | Replaces cash-fraction sizing |
| Pause vs Halt semantics | Relates to kill switch in CONTEXT.md |
| Universe rules: GBP equity ETFs, currency from metadata | Relates to 0008 |
| Data sources by market: Yahoo primary for LSE, Twelve Data for US only; symbol mapping layer; freshness rules (D25) | Supersedes 0008 for LSE. **Written: ADR 0017** |
| In-app backtest hidden; research external; demo as forward test | New |
