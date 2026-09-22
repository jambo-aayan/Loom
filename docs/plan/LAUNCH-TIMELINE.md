# Loom launch timeline

Every phase ends on a condition, not a date. Durations are estimates of how long the conditions usually take. Move on as soon as a condition is met.

## At a glance

| Phase | What | Est. duration | Cumulative |
|---|---|---|---|
| 0 | Foundation: safety, sizing, exits, fence, notifications | 1–2 weeks | ~2 weeks |
| 1 | Four strategies running in demo | 1–2 weeks | ~1 month |
| 2 | Demo tracking + new UI | 8–12 weeks | ~3–4 months |
| 3 | Live with £1,000, strategy by strategy | ongoing | from ~month 3–4 |
| 4 | Scale: more budget, capital lending, research | by milestone | ~6 months + |

**First real-money trade: roughly 3–4 months from starting the build**, if the evidence holds.

## Phase 0: Foundation

Deployment fixed, exit enforcer, budget fence, sizing rewrite, instrument groups, pause/halt, notifications working, dead-man's switch, backtest hidden.

**Done when:** a full demo day runs with three test positions exiting correctly (one on target, one on stop, one on time), with no duplicate orders, the fence holding, and notifications reaching your phone.

## Phase 1: Strategies into demo

Deep Dip, Compounder, Crash-buyer active in demo; Squeeze Breakout in shadow. Old strategies retired. In parallel, Deep Dip re-tested on real open prices and the wider universe.

**Done when:** all four have been generating signals for 5 trading days and a sample of 10 signals checks out against an independent recalculation.

## Phase 2: Demo tracking

New UI built. Research vs reality, daily summary, fee reconciliation, time-exit tracking, instrument page, Settings.

- **Week 4 checkpoint:** no missed exits, duplicate orders, fence breaches or silent missed runs.
- **Approvals:** manual for each strategy's first ~10 trades, then auto for the Compounder (its signals arrive during your working day and expire within the hour).

### Promotion gate (per strategy)

| Check | Bar |
|---|---|
| Demo trades | Compounder 30 · Deep Dip 20 |
| Avg return per trade | At least half of the research figure |
| Win rate | Within 10 points of research |
| Real cost | At most 2× modelled |
| Incidents | None in the last 4 weeks |

Research figures to compare against: Deep Dip 82% win, +0.87% avg; Compounder ~78% win, +0.54–0.77% avg.

- **Crash-buyer** only fires in market falls, so it can't hit a trade count in calm markets. It goes live on **"mechanics verified"** (signals, orders and exits proven correct in demo) at its small allocation.
- **Squeeze Breakout** stays in shadow until its sample is meaningful.

### Expected time to gate

- Compounder: ~150–250 trades/year → 30 trades in roughly 6–10 weeks.
- Deep Dip: ~25–45 trades/year on the original universe; more on the wider one (being tested). 20 trades could take 4–8 months at the low end, which is why the wider-universe test matters.

## Phase 3: Live with £1,000

- You enable live trading yourself (typed confirmation); Claude Code never does.
- Each strategy goes live individually when it passes its gate. Likely order: Compounder, then Deep Dip, then Crash-buyer.
- **First two weeks: manual approval for everything**, to watch real fills. Then back to auto for the Compounder.
- Same Balanced risk profile as demo.

**Stop rule:** if a strategy's live average return per trade is negative after 50 trades, it goes back to demo.

## Phase 4: Scale

### Budget growth rule (decided now, not on mood)

| Step | Condition | Budget |
|---|---|---|
| Start | Gates passed | £1,000 |
| 1 | 100 live trades; realised avg return ≥ half of research; drawdown within limits | £2,000 |
| 2 | Another 100 trades, same conditions | £5,000 |
| Beyond | Same pattern | Your call |

As the budget grows: more slots per strategy (fewer skipped signals), then capital lending.

### Research backlog
Intraday entry timing for Deep Dip, VIX for the Crash-buyer, economic-calendar filter, wider ETF universe, Squeeze sample size.

## What to expect in pounds (£1,000, Balanced)

Rough, assuming research holds (it usually looks better than reality):
- Compounder: 150–250 trades × ~0.5% × £100 ≈ **£75–125/year**
- Deep Dip: ≈ **£25/year** (more with the wider universe)
- Crash-buyer / Squeeze: lumpy, near zero in calm years

Roughly **£100–150 a year on £1,000**. The first year is about proving the edge is real with real fills; the budget growth rule is what turns a proven edge into meaningful money.

*Not financial advice. Past performance in backtests does not guarantee future results.*
