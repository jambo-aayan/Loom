# 18. Exit enforcement: a shared layer, on its own schedule

## Status

Accepted

## Context

`ExitPlan` was enforced in exactly one place — `check_exit` in the backtest engine. Nothing in
`trading_pass.py`, `risk.py` or `execution/` ever closed a live position on a target, stop or time
limit. Live exits existed only where a strategy happened to re-derive them itself, which three of
five did (Compounder, Harvester, Dip-Buyer, each with its own copy of the same `change_pct`
check). Trend Follower and Volatility Breakout did not, so their positions had no exit path at
all: their only coded exits were a death cross and a band normalisation, and their configured
`stop_loss_pct` and `time_exit_days` were dead values.

That produced a worse failure than a missing stop. The backtest *did* enforce the plan, so
backtest results described a system that did not exist — measured over 2019-2024, 46 of Trend
Follower's 51 exits came from the stop or the time exit, mechanisms live trading did not have.
The mechanism we intend to use for deciding whether a strategy is worth promoting was measuring
a different strategy.

Exits were also on the entry schedule: one pass per weekday at 08:00 UTC. A 2% stop checked once
a day is not a 2% stop.

## Decision

### A shared enforcement layer, not per-strategy exits

Plan-based exits move to one layer that reads `ExitPlan`, sharing its logic with the backtest
engine so live and backtest agree by construction. Strategies keep exits that a plan genuinely
cannot express — a death cross, a volatility regime change — and emit those on top.

Two alternatives were rejected. Leaving exits with each strategy (fixing the two that lack them)
keeps five copies of one rule and preserves the backtest/live divergence. Centralising
*completely*, with strategies forbidden from emitting exits, would discard the discretionary
exits, which are real signals and not reducible to target/stop/time.

### Its own schedule

A separate exit job runs every 30 minutes between 08:00 and 21:00 UTC on weekdays — one window
spanning both the LSE and US sessions. The interval is configurable; a per-exchange window is the
better answer but needs instrument metadata that does not exist yet, and outside an instrument's
own hours the broker price simply does not move, so a check then is a no-op rather than a wrong
answer.

Entries stay on the daily pass. They are patient by design (ADR-0002); exits are not, and
treating them alike is what made a low-volatility strategy with a tight stop behave
unpredictably.

### Plan-based exits execute without approval

ADR-0009 already held that an exit realising a pre-calculated outcome is "arithmetic, not a
forecast". The code did not act on it: `_decide_approval` made no entry/exit distinction, so
under the default `manual` mode a stop-loss queued for a human click and `expire_stale_signals`
discarded it after 24 hours. A stop that waits for a click is not a stop.

So plan-based exits auto-execute; discretionary exits still follow the strategy's `Approval
mode`. This narrows the **Auto-trading gate** to entries and discretionary exits, recorded in
`CONTEXT.md`: a circuit breaker that blocked you from closing a losing position would be the
wrong shape.

Two things do *not* change. The **kill switch** stays absolute and continues to block exits, even
though the daily-loss limit auto-engages it — so exactly when a day goes badly, stops stop. That
perversity is real and was accepted deliberately: the kill switch's value is being unconditional,
and an emergency is the worst moment to have to recall which half of it still fires. The layer
must therefore not *propose* while engaged, or it manufactures a failed `Order` every 30 minutes.
The consequence is that manual trading becomes more urgent, since there is currently no way to
close a position from Loom while the kill switch is on. And every exit still passes the full
risk/sizing re-check before submission.

### Supporting decisions

- **Prices** come from Trading 212's `currentPrice` (one call for all holdings), falling back to
  Twelve Data — the same number Loom already displays as P&L, so an exit cannot fire off a
  different price than the one on screen.
- **Trailing stops** are in scope: `ExitPlan` gains `trailing_stop_pct` alongside
  `stop_loss_pct`, either able to fire, so a strategy can cut a bad entry quickly *and* let a
  winner run. The high-water mark is **derived** as `max(high)` since entry rather than stored:
  no new mutable state, and a missed run or restart cannot corrupt it.
- **A `Signal` realising an exit plan is still a `Signal`**, attributed to the `Strategy` owning
  the `Book` that holds the position — it realises that strategy's own plan. This needs no schema
  change, and avoids a nullable `Order.signal_id`, which would break `booked_trade_for_signal`,
  History and per-`Book` P&L, all of which traverse `Order → Signal`.
- **An exit never expires** while its position is open, and is withdrawn if the position closes by
  another route. An entry expires because the opportunity passes; an exit's reason does not — the
  trend ended and you still hold. Expiring it discards the judgment and silently defaults to
  "hold", which is the one outcome nobody chose.
- **Every auto-executed exit notifies**, unconditionally and not gated by `Notify threshold`.
  That threshold filters *proposals* competing for attention; a completed exit is a fact about
  real money, and there is one per position rather than a stream.
- **Counterfactuals stay plan-only**, with the horizon derived from the plan rather than a fixed
  90 days. Re-running a strategy forward per rejected signal would improve two strategies out of
  five at considerable cost. `counterfactual.py`, `CONTEXT.md` and ADR-0011 were corrected: they
  claimed to apply "the originating strategy's own exit logic" while applying the exit plan.
- **Partial exits are out of scope.** The accounting already supports them —
  `reconstruct_closed_trades` does correct FIFO partial matching and `booked_trade_for_signal`
  aggregates by exit order. What is missing is a way for `ExitPlan` to express a tier, and a
  guard against a trim condition re-firing every 30 minutes and slicing a position to nothing.
  Deferred because it would mean designing a tier mechanism for `Volatility Harvester`, whose
  trim design is itself unresolved (see the stop/add-threshold conflict in
  `docs/strategy-and-universe-gap-analysis.md` D2). When built, the re-fire guard should follow
  the same derive-don't-store approach as the trailing stop's high-water mark.

### Rollout

Enforcement applies **retroactively** to open positions: they are precisely the ones with no exit
today. But it ships in a **dry-run mode first**, logging what it would have done without selling,
because Compounder's `stop_loss_pct=0.02` is roughly 1.3 daily sigma for a low-volatility
instrument and was the most common exit in backtest. Turning enforcement on could close existing
positions immediately — not because enforcement is wrong, but because that parameter is. The dry
run validates the layer against real prices before it can act, and the Compounder deep dive should
land before it goes live.

## Consequences

- The `change_pct` checks in Compounder, Harvester and Dip-Buyer are deleted; their plan-based
  exits come from the shared layer. Harvester's z-score trim and the crossover/normalisation exits
  in Trend Follower and Breakout stay, as discretionary exits.
- `ExitPlan` gains a field and `check_exit` gains a trailing-stop branch; both are shared with the
  backtest engine, so a change to exit semantics now changes both paths at once. That is the
  point, and it also means exit logic becomes a place where a mistake is expensive in two
  directions.
- Enforcing plans reveals parameter choices that were previously inert. Harvester's add-on-weakness
  becomes unreachable, because its stop (5%) fires before its add threshold (z ≤ −2.5) is reached —
  so story 22's always-manual add and its `max_add_ons` cap become dead code until the deep dive
  resolves it. Expect more of this: every strategy's stop was chosen while nothing enforced it, so
  none of them ever had feedback. The dry run is the first such feedback these parameters have
  had, and should be treated as a parameter audit as much as a correctness check — see
  `docs/strategy-and-universe-gap-analysis.md` D0, which lists what to record and which
  parameters are already suspect.
- A new scheduled job and a configurable interval mean Settings needs an editable numeric control,
  which it currently has none of — thresholds render as read-only text. This rides with the
  Settings write path rather than being separate work.
