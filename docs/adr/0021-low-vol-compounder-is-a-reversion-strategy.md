# 21. The Low-Vol Compounder is a reversion strategy, not a drift harvester

## Status

Accepted

## Context

The first of the five per-strategy deep dives. It went further than expected, because the
strategy as built has no edge.

`LowVolCompounder` buys when 20-day realized volatility is at or below 0.015 and the close is at
or above its 50-day average, and exits on a 4% target, a 2% stop or a 30-day limit. Both entry
conditions describe a calm asset in an uptrend — a state an index tracker is in most of the time.
The entry therefore fires close to at random, and a randomly-timed long position earns market
drift and nothing else.

Simulated over one instrument and one year at 8%/yr drift, with immediate re-entry after each
exit and the round-trip costs from ADR 0019:

| daily vol | round-trip cost | buy & hold | Compounder | trades/yr | fees paid |
| --- | --- | --- | --- | --- | --- |
| 0.008 | 0.30% | **+8.11%** | +2.96% | 17.2 | 5.17% |
| 0.012 | 0.30% | **+8.15%** | −0.61% | 29.2 | 8.75% |
| 0.015 | 0.30% | **+8.17%** | −3.72% | 39.9 | 11.97% |
| 0.012 | 0.08% | **+8.37%** | +5.96% | 29.2 | 2.33% |

It loses to buying the same instrument and doing nothing, at every volatility and every cost base
tested. At the volatility its own gate permits, on a US-priced instrument, it converts a +8.2%
year into −3.7% while paying 12% in fees.

Three supporting facts, each of which independently condemns the current design:

- **The barriers contribute nothing.** At zero drift the 4%/2% pair returns −0.11% net per trade.
  A target-and-stop pair on a driftless walk is expectancy-neutral by construction; only drift
  makes it positive. The realized win rate is 39%, not the "small, consistent gains" the
  docstring claims — 59% of trades hit the stop.
- **It cannot clear ADR 0019's cost floor at any setting.** The best pair found (8%/4%/60d) yields
  0.94% gross against a 0.30% cost — 3.1×, against a bar of ~10×. Drift pays ~8%/252 per day
  held, so a pure drift harvester needs a four-month average hold to clear that floor. This one
  holds 8.9 days.
- **The gate does not mean what its name says.** A 0.015 daily threshold is 23.8% annualised —
  an average single stock, not a low-volatility one; the S&P runs around 16%. And after ADR 0019
  it points the wrong way: with volatility-scaled barriers, expected value per trade *rises* with
  volatility, because the barriers widen with it while cost stays fixed.

The last row of the table is the one that decided the design. Changing nothing but the cost base
moves the strategy from −0.61% to +5.96%. For a design built on many small trades, the cost base
is worth more than any parameter in it.

## Decision

### The entry buys weakness inside strength

The 50-day trend filter stays as a regime condition, and an entry now additionally requires the
close to be meaningfully below its own short-term (10-day) average. The strategy buys a
dislocation inside an uptrend rather than the uptrend itself, which gives the entry something to
predict: short-horizon reversion pays out in days, and days is the only timescale on which a
days-long hold can be funded.

Rejected: a z-score against a 20-day mean, which is the Volatility Harvester's own rule and would
make the two strategies near-duplicates; and an N-consecutive-down-days count, which is cruder
and gives no natural target.

This overlaps the Harvester more than is comfortable. The defensible line is universe and
behaviour, not indicator: the Harvester trades any instrument on deep dislocations and adds on
further weakness; the Compounder trades a narrow ETF list on shallow ones and never adds. The
universe decision below is what makes that line real rather than rhetorical.

### The universe is GBP-denominated ETFs, chosen for cost

A curated list of roughly 15-25 large, liquid, GBP-listed index trackers — not a volatility
screen, and not the whole GBP ETF shelf.

GBP-listed means no FX conversion (the instrument's currency matches the account's) and, being
ETFs, no stamp duty — leaving only spread, so a round trip costs on the order of 0.05-0.10%
against 0.30% for a US name. That is the change the table above says matters most. Curated rather
than exhaustive because niche and sector funds carry wider spreads, which would give back the
cost advantage that is the entire point.

The candidate list is in `docs/compounder-universe-candidates.md`. It needs validating against
T212's instrument metadata before it is committed — in particular the GBP versus USD line of each
fund, since picking the USD line silently reinstates the FX cost this decision exists to avoid —
which is the instrument-sync work that manual trading needs anyway (ADR 0022).

### Exit geometry inverts

Reversion designs are right often and small, which is what "small consistent gains" actually
looks like when it is true:

- **Target**: the short-term average the entry measured against — the thesis realised, rather
  than a percentage picked by hand.
- **Time exit**: 10 trading days. If it has not reverted by then the dislocation was a move, not
  a dislocation, and holding on is being long by accident.
- **Stop**: wide, around three times a typical day's move, frozen at entry.
- **Cooldown**: no re-entry into the same instrument for 3 trading days after any exit of it in
  this `Book`.

The cooldown is not tidiness. With a reversion entry, a stop-out means price fell, which deepens
the very dislocation the entry looks for — so without a cooldown a losing trade actively invites
its own repeat.

### The stop is an emergency brake, and is to be documented as one

The stop is deliberately not tuned for return. A stop in a reversion system is adversely
selected: it sells the bottom of the dip it bought. Measured across 3,000 simulated years with a
genuine reversion process, tightening the stop degrades expectancy monotonically — an 80% win
rate with no stop falls to 68% at a tight one.

Removing it entirely is nevertheless wrong. It buys about 0.1pp/yr, and sells the left tail: the
worst trade moves from −3.6% to −9.1% with no crash in the model at all, and to −30.7% once a
20-day crash regime arriving once every eight years is included. Across that crash hazard, having
the wide stop is worth about +1pp/yr.

The time exit is not a substitute. It caps how long the position is held, not how far it falls;
ten trading days at tripled volatility is that −30.7%. And a crash generates dip signals
continuously while the 50-day filter takes weeks to roll over, so the book keeps buying into it.

This is recorded explicitly because the stop will look useless in any backtest that contains no
crash, and the obvious "optimisation" is to tighten it. That would be exactly backwards.

### It emits entries only

The strategy's own exit loop is deleted; every exit it has is expressible as an `Exit plan` and
belongs to the enforcement layer (ADR 0018). Two things come with that deletion: the 30-day time
limit starts working at all — the strategy's loop checked target and stop but never the time
limit, so it has only ever fired in backtest — and exits move from daily to every 30 minutes.

That makes the Compounder the cleanest possible first test of the enforcement layer, since it
leaves no strategy-side exits to confound the dry-run observations.

### No regime exit yet

The alternative to a per-position stop is closing the whole `Book` when the 50-day trend filter
that justified every entry breaks. It is one decision instead of many and addresses the
buying-into-a-crash problem at its root, but it would give the Compounder a selling job back and
undo the clean separation above.

Deferred deliberately, with a trigger rather than a date: if the dry-run `ExitObservation`s show
the stop firing in clusters, that is a regime break appearing in real data, and that is the
moment to add it.

### Sizing, and automation

- **Allocation**: about 25% of total account value — holdings plus cash, per ADR 0020 — as the
  ceiling on what the Compounder may hold. Available cash caps what it can buy today but does not
  define the size.
- **Position count**: 8-10 open positions, flexed with account size so no position falls below
  the ~£50 minimum. A flat count would breach the minimum on a small account.
- **Approval mode**: `manual` initially, moving to `auto` once a few weeks of demo trading show
  the emergency brake behaving. Not because the design is doubted, but because nearly everything
  about this strategy is changing at once.

### `time_exit_days` counts trading days, and one lot per instrument per Book

Both already follow from ADR 0019 and ADR 0020 respectively; stated here because the Compounder
is the first strategy to depend on them. The one-lot rule must be scoped to this `Book` — other
`Book`s holding the same tracker is expected under ADR 0020's co-holding, and an unscoped check
would silently start blocking entries as the roster fills.

## Consequences

- **This design is unproven.** The measurements above come from simulation, not market data —
  the network policy in the session where this was designed could not reach a price source. The
  *direction* of each result is robust, but the existence, depth and speed of short-horizon
  reversion in GBP trackers is an assumption. It must be measured on real data covering at least
  2018-2025, including 2020 and 2022, before this ships. If the reversion is not there, or does
  not survive a 0.08% cost, the honest outcome is that this strategy should not exist and the
  low-vol universe should fold into a Harvester variant.
- The crash figures depend on an assumed hazard rate of roughly once every eight years. The sign
  of the conclusion does not depend on it; the magnitude does.
- Backtest comparisons against the old Compounder are meaningless — this is a different strategy
  wearing the same name. Its `Strategy config version` history starts fresh.
- The instrument universe now blocks this strategy, and the same instrument-sync work unblocks
  manual trading (ADR 0022), the hardcoded universe (gap A1), instrument metadata (A6) and the
  unmapped-ticker failure on the live ISA (A4).
- The strategy's confidence formula must be rebuilt around the new entry, and is subject to
  ADR 0020's amendment on `Expected value`.
