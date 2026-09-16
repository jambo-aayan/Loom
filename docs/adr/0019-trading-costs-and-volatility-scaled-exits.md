# 19. Trading costs, and exit levels in volatility units

## Status

Accepted

## Context

Two findings from a cross-strategy design review, kept in one ADR because they are the same
mistake seen from two sides: every level in the system is a percentage, and no percentage in the
system knows what it costs to reach.

### Nothing in Loom knows a trade costs money

`Order` records quantity and fill price. `Trade` computes P&L as `(exit - entry) × quantity`.
The backtest engine does the same. Every number Loom shows — realized P&L, a `Book`'s
performance, a `Counterfactual outcome`, the promote/demote comparison between two
`Strategy config version`s — is a gross figure presented as if it were a net one.

Trading 212's actual charges, as they stand:

| Charge | When | Rate |
| --- | --- | --- |
| Commission | never | £0 |
| FX conversion | each way, on any instrument not priced in the account's currency | 0.15% |
| UK stamp duty | on purchase, UK **shares** only — not ETFs | 0.5% |
| Spread | each way, always | instrument-dependent |

A round trip in a US-listed name is therefore ~0.30% before spread; a UK share adds 0.5% on the
buy. This is not a rounding error against the designs in the roster. The Low-Vol Compounder's
configured profit target is 4% — a US round trip eats ~7.5% of a winning trade, and the strategy
is explicitly designed to trade often. A design that wins 0.4% per trade on a 0.3% cost base is
not a small edge; it is a fee-generation machine that reports itself as marginally profitable.

The dangerous case is not the reported number being slightly wrong. It is promotion: a
`Strategy config version` is promoted by comparing measured performance, and if the measurement
is gross, we will systematically promote whichever variant trades most.

### Every level is a percentage, and a percentage means something different per instrument

Each strategy's `DEFAULT_PARAMS` carry fixed percentages: Compounder 4% target / 2% stop,
Harvester 6%/4%, and so on. These were chosen by judgment, applied to every instrument in the
universe identically.

A 2% stop is roughly 1.3 daily standard deviations for the low-volatility, large-cap names the
Compounder is pointed at. On a high-beta name it is comfortably inside a single day's noise. The
same number means "a real move has gone against me" on one instrument and "it is Tuesday" on
another. With the universe about to widen well past its current four instruments (gap A8), the
spread of volatilities the same constant has to cover widens with it.

This was survivable while nothing enforced the plan. ADR 0018 changed that: the stop is now a
real instruction that will close a real position, on a 30-minute cadence rather than daily. The
one exit that was most common in the 2019-2024 backtest is now the one most likely to fire on
noise.

## Decision

### Costs are recorded, and separately modelled

Two different things, deliberately not conflated:

- **Recorded.** `Order` gains fields for what the broker actually charged, taken from the fill
  response rather than computed by us. Realized P&L on a `Trade` is net of the recorded charges
  on both legs. This is ground truth and follows ADR 0003: the broker is the authority on what a
  trade cost, exactly as it is on what it filled at.
- **Modelled.** Backtests and `Counterfactual outcome`s have no fills to read, so they apply a
  cost model — the table above, per instrument, from its currency and type. A counterfactual
  must be net for the same reason a `Trade` must: `History` exists to compare "what you rejected"
  against "what you approved," and measuring one gross against the other net would flatter every
  rejection by the cost of the trade that never happened.

The model is an assumption and is labelled as one. Once enough real fills exist, the recorded
charges are the check on it.

### Plan levels are gross

An `Exit plan`'s target and stop describe price movement, not net return. A 4% target means the
price moved 4%.

The alternative — net targets, where the plan holds until the position clears costs — was
rejected. It makes the exit level a function of position size and entry cost, so the same plan
means different things for different fills, and it silently turns "I was wrong about this trade"
into "hold until it pays for itself," which is the exact behaviour a stop exists to prevent.

Costs are instead a **design-time** constraint, not a runtime one.

### A cost floor at promotion

When a `Strategy config version` is promoted, its expected win per trade is checked against the
`Round-trip cost` of the instruments it trades. A design whose typical win is not a comfortable
multiple of its own cost — on the order of 10× as a starting bar, tuned once there is real data —
does not get promoted.

Promotion is the right gate because it is when the design is chosen. Catching this in realized
P&L means catching it after the money is gone, and catching it per-signal means blocking trades a
strategy will keep proposing forever, since the problem is the strategy, not the signal.

### Exit levels are volatility multiples, and the measure is ATR

Both stops and targets are expressed in multiples of the instrument's own volatility.

Targets, not just stops, because the two are one decision. A target fixed in percent against a
stop scaled in volatility gives a reward:risk ratio that drifts with every instrument — the same
config would be a 3:1 trade on a quiet name and 0.5:1 on a volatile one, and the strategy's
edge would silently become a function of which instruments happened to be in the universe.

**ATR** is the measure, for exits specifically. It uses the true range, so it counts overnight
gaps — which is what actually takes out a stop — where a close-to-close standard deviation does
not. It is also already computed for the Volatility Breakout's squeeze detection.

This is scoped to exits. Entry gates keep whatever measure their logic is built on (the
Compounder's realized-volatility screen, the Breakout's band width) — those measure a different
thing, and forcing one measure across both would be tidiness at the cost of correctness.

### Migration is additive

Sigma-denominated fields land alongside the existing percentage fields rather than replacing
them. Both are populated during the transition; enforcement reads the sigma fields once each
strategy's deep dive has set them.

A hard cutover would require choosing multipliers for all five strategies at once, before any of
their deep dives, which is how the current arbitrary constants got here in the first place. It
would also invalidate stored plans on open positions mid-flight, and make historical signals
unreadable against the new fields.

### `time_exit_days` counts trading days

It is currently read as calendar days, which makes the same config a different holding period
depending on where it lands against a weekend or a bank holiday. Every other window a strategy
uses is measured in bars; the time exit now matches.

## Consequences

- `Order` grows fee fields and every P&L path — `Trade`, `Book` performance, counterfactuals,
  the promote/demote comparison, the UI — reads net. Existing rows have no recorded fees; they
  are gross and must be treated as such rather than assumed to be zero-fee.
- Backtest results will get worse, correctly. High-frequency designs will get worse the most,
  which is the point. Any prior comparison between strategies was measuring gross and is not
  comparable to post-change numbers.
- The cost model needs per-instrument currency and type (share vs ETF) to know whether stamp
  duty applies — a small addition to instrument metadata, and one more reason the universe
  expansion needs real metadata rather than a hardcoded list.
- Exit enforcement stays in dry run until at least the Low-Vol Compounder's multipliers are set
  (ADR 0018), since its 2% stop is the specific level this ADR says is mis-scaled.
- Every strategy deep dive now has a fixed question to answer: how many ATR for the stop, how
  many for the target, and does the resulting expected win clear the cost floor.
