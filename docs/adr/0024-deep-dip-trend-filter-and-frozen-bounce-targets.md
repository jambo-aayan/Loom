# 24. Deep Dip: a trend filter, a gated add, and frozen bounce targets

## Status

Accepted. Amends ADR 0021.

## Context

The Volatility Harvester deep dive, which existed to answer one question: after ADR 0021 turned
the Compounder into a dip-buyer, are these two strategies one strategy wearing two names?

They are not, and the reason is not the one ADR 0023 assumed.

### An exit that cannot be executed

ADR 0021 states both that the dip strategies' profit target is "the short-term average the entry
measured against" and that the strategy emits entries only, with every exit owned by the
enforcement layer. Those cannot both hold. The enforcement layer reads `ExitPlan`, which
expresses a fixed percentage from entry, a stop, a trailing stop and a time limit. "Sell when
price returns to its 10-day average" is a *moving* level and is none of them. The Harvester has
the same problem in a different notation: its exit is `z >= -0.2`, also relative to a rolling
mean.

Left alone this produces either a strategy whose main exit silently never fires, or a quiet
return of exit logic to the strategies, undoing ADR 0018.

### The difference between the two dip strategies is the trend filter

Measured over 900 simulated years, with regimes that can turn genuinely negative:

| | Steady Dip | Deep Dip (Harvester) |
| --- | --- | --- |
| Entry days | 21,402 | 23,121 |
| Days **both** want to buy | &mdash; | **748 (3.2%)** |
| Entries made in a downtrend | 12.4% | **48.6%** |
| Avg 10-day move after entry | +0.26% | +0.56% |
| Avg 10-day move, downtrend entries only | — | **−0.39%** |

The overlap is negligible, and the reason is that Steady Dip requires price above its 50-day
average while the Harvester has no trend condition at all. Nearly half the Harvester's entries
are in falling markets, and those entries lose money — they are dragging down a signal that is
otherwise the stronger of the two.

Applying a trend filter to both separates them completely: Steady Dip fires 16,529 times, Deep
Dip 605. A deep dislocation that is *still* above its 50-day average is roughly 27 times rarer
than a shallow one. The pair is frequent-and-shallow versus rare-and-deep, which is a real
distinction and exactly the shape ADR 0023's shared-implementation plan was designed for.

### The add-on-weakness concentrates into falling markets and earns nothing

ADR 0009 made this action always-manual on the grounds that it is where being confidently wrong
compounds fastest. That instinct was right and the measurements are worse than the instinct:

- It fires on **18%** of entries — not a rare edge case.
- **58% of adds land in a downtrend**, against a 48.6% base rate: the add specifically selects
  for falling markets.
- It earns nothing for that risk — **+0.80%** over the following 10 days after an add, against
  **+0.73%** for entries where it never fired.

There is also a mechanical quirk: the exit condition is evaluated before the add, so once a
position is down 5% the add can never fire. It is pre-empted on 11.8% of entries. The add exists
only in a narrow band — deep enough to trigger, not deep enough to stop out.

### "Trim" is documented but not implemented

The module docstring and ADR 0009 both say the Harvester trims on a bounce. `_exit_signal`
carries no quantity, so the risk layer sells the whole position. The strategy can add on the way
down but cannot scale out on the way up — asymmetric in the wrong direction.

## Decision

### Bounce targets are frozen at entry (amends ADR 0021)

At entry, the distance to the reference level — the 10-day average for Steady Dip, the rolling
mean for Deep Dip — is measured once and stored as an ordinary percentage profit target. The
enforcement layer then handles it with no new capability.

This follows what has already been decided twice: a plan is fixed at the moment of entry
(`CONTEXT.md`), and the volatility its levels scale from is measured once and never re-measured
(ADR 0019). The cost is that the reference drifts during the hold, so the target is slightly
stale by the end of a 10-day position — a second-order effect.

Rejected: teaching the enforcement layer to recompute indicators. It would drag strategy logic
back into the layer ADR 0018 exists to keep clear of it, and make a plan that cannot be
reconstructed after the fact from what was known at entry.

### Deep Dip gets the same trend filter as Steady Dip

One condition, already written in the sibling strategy, removing the half of the Harvester's
behaviour that loses money.

### The add is gated behind the trend filter, not removed

In an uptrend, adding into a deeper dip is the strategy's own thesis applied twice, which is
coherent. In a downtrend it is doubling down on being wrong, which is what the measurements
show it mostly does. It stays always-manual regardless of `Approval mode`, per ADR 0009.

If it still shows no benefit once trend-filtered, it should be removed at the next review. This
ADR does not pre-commit to keeping it.

### The two dip strategies both stay, as configurations of one implementation

Confirmed as planned in ADR 0023: Steady Dip is shallow, frequent, GBP trackers, no adds; Deep
Dip is deep, rare, wider universe, adds enabled and gated.

### Exits become partial

The code changes to match the documentation rather than the reverse. FIFO partial matching
already works correctly in `reconstruct_closed_trades`; the blocker was the risk layer
overriding the quantity on sells. A strategy that scales in should be able to scale out.

## Consequences

- **The reversion assumption is still unmeasured, and now two strategies rest on it.** The
  simulation used here has mean reversion built into its generator, which rewards deeper dips by
  construction — so the finding that Deep Dip's entry is the stronger signal (+0.95% against
  +0.33% like-for-like, both trend-filtered) is the least trustworthy number in this ADR and must
  not be acted on before real data. The structural findings — no trend filter, half the entries
  in downtrends, the add selecting for falling markets, the negligible overlap — do not depend on
  that assumption.
- With the trend filter added to Deep Dip, **every strategy in the roster now requires an
  uptrend to do anything.** In a sustained downturn the whole roster sits in cash. That is a
  defensible position for this account and it is now a deliberate one, but it should be a
  conscious choice rather than an emergent property nobody noticed.
- Partial exits need the risk layer's sell path to honour a requested quantity — a small change,
  but it touches the one function every order flows through.
- Deep Dip's entry threshold, hold length and stop still need setting in the units ADR 0019
  requires. They are not set here because they should be set against real data, alongside Steady
  Dip's, in one measurement rather than two guesses.
