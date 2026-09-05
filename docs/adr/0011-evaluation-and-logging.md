# 11. Evaluation layer: full logging, counterfactuals, config versioning, and drill-down

## Status

Accepted

## Context

With the strategy roster settled (ADR 0009) and portfolio attribution decided (ADR 0010), the
remaining open area is whether the system tells the user anything useful about whether it's
actually working, and whether the user's own approve/reject judgment is adding value. Two
conversations converged on the same layer: wanting a place under each strategy that explains its
logic and current parameters (to support fine-tuning), and wanting every action *and every
recommendation* — including ones never acted on — logged and evaluable in hindsight, with the
ability to leave a note on why a decision was made, plus drill-down by instrument/sector, not
just by `Book`.

## Decision

### Full logging, nothing purged

Every `Signal` is retained permanently regardless of outcome (`approved`, `rejected`, `expired`,
or auto-executed) — see the updated `Signal` entry in `CONTEXT.md`. `History` is not just a log
of executed trades; it's a log of every recommendation the system ever made, whether or not the
user acted on it.

### Counterfactual outcomes for signals never executed

A rejected or expired `Signal` keeps being tracked as a shadow position: Loom simulates it
forward using the same simulated-fill mechanics the backtest engine already has, applying the
originating `Strategy`'s own exit logic against real subsequent market data, until it would have
exited or a max horizon is reached. The resulting hypothetical outcome is attached to the
`Signal` record. This is deliberately a learning tool aimed at the user's own decision quality,
not just the strategy's — "I rejected this and it would have gained X%" is exactly as visible in
`History` as "I approved this and it gained Y%." No new simulation engine is needed; this reuses
the backtest engine's fill logic on a single-signal, forward-in-time basis instead of a
historical batch.

### Notes on every decision

At the moment a `Signal` is approved or rejected, the user may attach an optional free-text
`Note`. Combined with the counterfactual outcome, this is what makes `History` function as a
genuine trade journal (a separate "journal" feature is unnecessary — this *is* the journal,
attached to the actual decisions rather than a disconnected diary).

### Strategy config versioning

Every change to a `Strategy`'s parameters creates a new numbered `Strategy config version`.
Every `Signal` and backtest run records which version produced it. This powers a **Strategy
detail page**: plain-English explanation of the logic, current parameters with a short
description of what each one controls, and a changelog of prior versions with how performance
compared across the change — not just "performance changed at some point," but "changed *because
of this specific parameter change*, here's the before/after."

### Evaluation metrics and benchmark comparison

Beyond raw return, the Performance/Overview layer needs risk-adjusted metrics computed per
`Book` and in aggregate: max drawdown, win rate, profit factor, expectancy per trade, rolling
Sharpe/Sortino, and a correlation view across `Book`s (are the strategies actually
diversifying, or all moving together). Every performance chart plots against a benchmark
(e.g. a FTSE 100 or global tracker) — return without a benchmark is close to meaningless for
judging whether a strategy is adding value versus just following the market.

### Portfolio drill-down

Performance and History are both sliceable by more than one dimension: by `Book`
(strategy/manual), by individual instrument, and by **sector/industry** — a new piece of
instrument metadata not previously needed. `yfinance`'s `info` payload includes sector/industry
classification for free and fits the existing market-data provider boundary, so this needs no
new external dependency, matching the same reasoning as the fundamentals data in ADR 0009. This
also gives a natural point of comparison against the user's pre-existing sector-segmented T212
Pies (`Manual` `Book`, per ADR 0010) — e.g. total exposure to semiconductors across both
bot-managed and manual holdings combined.

### Insight upgrades

Two additions to `Insight` beyond the advisory commentary already specced: the trigger an
`Insight` explains is annotated directly on the instrument's price chart (marking the exact
point RSI crossed a threshold, a moving-average cross, etc.) rather than described only in text;
and a rolled-up daily/weekly digest view summarizing what fired and what the LLM is watching,
alongside the existing per-signal commentary.

## Consequences

- `Signal` records need to stay live/trackable indefinitely after their decision (for
  counterfactual simulation), not archived once decided — a background job keeps updating
  shadow positions until they resolve or hit the max horizon; this is ongoing computation, not
  a one-time write.
- Instrument metadata gains a sector/industry field, sourced from `yfinance`.
- The dashboard mockups need a new **Strategy detail page** (explanation, parameters, config
  version changelog) and expanded Performance/History views (benchmark overlays, drill-down by
  instrument/sector, counterfactual outcomes and notes shown per `Signal`) — meaningful new
  design surface beyond what's currently mocked up.
- This is a genuine v1 scope increase, same as ADR 0009/0010 — the published spec (issue #1)
  needs to be revisited to reflect all three ADRs together rather than patched piecemeal.
