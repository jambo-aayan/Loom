# Does short-horizon reversion exist? — test findings

Status: **the real-data test did not run.** Both market-data providers are unreachable from this
environment. What follows is therefore not the measurement ADR 0021 asked for. It is what could
be established without prices — which turned out to be more than expected, and bad for both dip
strategies.

Harness: `docs/analysis/reversion-test/`. Runs: `docs/analysis/reversion-test/out/`.

## The blocker

The production stack — `PrimaryWithBackfillSource(TwelveDataSource, YFinanceSource)`, unmodified
— resolved **0 of 22** candidate tickers. Every request is refused at the egress proxy:

```
api.twelvedata.com:443      connect_rejected (403)
query1/2.finance.yahoo.com  connect_rejected (403)
```

Also probed and blocked: stooq, Alpha Vantage, Polygon, marketstack, Nasdaq Data Link, Tiingo,
FMP, LSE, FT. The session's allowlist is GitHub, the package registries and the Anthropic API.
No ticker resolution, no currency check, no GBP-vs-USD line verification — the whole of the doc's
"verify which tickers actually resolve" step is untouched.

This is the same wall ADR 0021 hit ("the network policy in the session where this was designed
could not reach a price source"). It needs an environment with egress to a price provider, or a
cached price dump committed from somewhere that has one. The harness reads a cache, so producing
one anywhere unblocks everything here.

## What the harness does differently

One thing, and it is the thing that matters: **it measures every entry against a baseline.**

ADR 0021 and ADR 0024 report the average move after an entry — Steady Dip +0.26%, Deep Dip
+0.56% — with nothing to compare against. But the expected forward return after *any*
price-conditioned entry into a rising asset is just that asset's drift over the holding window.
An index tracker returning 8%/yr drifts +0.32% per 10 trading days *after every kind of day*,
dip or no dip. A dip-buying rule that returns +0.26% over 10 days has not found a bounce. It has
found slightly less than the drift it would have earned entering at random.

So every number below is reported as an **edge over random entry** into the same instrument in
the same year, with a 95% interval bootstrapped over whole (instrument, year) blocks — dip days
cluster hard in time, and across funds tracking the same index, so an iid interval would be far
too narrow.

The entry rules are reproduced exactly as `loom/strategies/` computes them, including that every
window includes the current bar.

## The controls

With no prices, the harness was run against three synthetic processes. **None of these are
evidence about real ETFs.** They are calibration: they say what each number looks like when the
answer is known in advance.

| control | what it is | reversion |
| --- | --- | --- |
| `null-drift` | the repo's own `FixtureMarketDataSource` | **none** |
| `null-zero` | same, drift removed | **none** |
| `reverting` | AR(1) transient deviation, 6.6-day half-life | **strong** |

The positive control exists so that "no edge found" cannot be confused with "the harness is
broken". It is not: the harness detects the reversion in `reverting` through the Deep Dip entry
(+0.24% edge) and correctly reports none in the nulls (+0.04%, +0.03%).

## Findings that hold without market data

### 1. ADR 0021's headline number is exactly what *no* reversion produces

`null-drift` — a random walk with no reversion whatsoever — gives Steady Dip a mean 10-day move
of **+0.26%**. ADR 0024's table reports **+0.26%**.

The edge over random entry in that control is +0.04%, CI [−0.08%, +0.14%]: zero, as it must be
for a process that cannot revert. The raw number and the null are indistinguishable because the
raw number *is* the null — it is drift, measured and reported as a bounce.

The precise coincidence is luck. The point is not the decimal place: it is that a +0.26% average
10-day move is fully accounted for by drift, so it was never evidence of anything, and no
baseline was computed that would have shown this.

### 2. The ~70% win rate is exit geometry, not reversion

The design assumes a win rate near 70%. The controls:

| control | reversion | Steady Dip win rate | mean gross |
| --- | --- | --- | --- |
| `null-zero` | none, no drift | **68.1%** | −0.34% |
| `null-drift` | none | **70.1%** | −0.24% |
| `reverting` | strong | 75.3% | −0.06% |

A 70% win rate is what a **driftless random walk** produces. It is a mechanical consequence of
the exit shape: a frozen target roughly 0.5% above spot is reached by noise most of the time,
while the 10-day time exit lets the losers run their full distance. High win rate, negative
expectancy — a −0.24% mean gross trade that wins 70% of the time.

Hitting 70% on real data would confirm nothing. It is the null.

The same applies to "how often price recovered to the 10-day average", the metric the test was
framed around: 65.4% with no reversion, 70.9% with strong reversion. A 5.5pp spread between
"none" and "lots" makes it close to useless as a discriminator. The distance to the target is
small enough that noise touches it either way.

### 3. Steady Dip cannot clear ADR 0019's bar even if it never loses

This one is arithmetic, not simulation.

The frozen bounce target is the distance from the close to its own 10-day average. At the
volatilities these funds run, that distance averages **0.56%–0.80%** across the whole candidate
list (**0.63%–0.89%** equities only). ADR 0019's promotion floor is 10 × 0.08% = **0.80%**.

So the ceiling on Steady Dip's mean gross trade — the number it would earn if *every single
entry* hit its target and none ever lost — is about **7–10× cost**, against a bar of 10×. The
strategy aims at a target smaller than the number it has to beat. Any loss at all puts it under,
and the controls put it at 0–0.5×.

Deep Dip is not in this trap: its target averages 1.26%–1.70%, a ceiling of 16–21×.

This depends on the assumed volatility (15% for equity trackers, 6% for gilts). Those are the
right neighbourhood, but it is the first thing to check against real prices, because the whole
finding scales with it.

### 4. No plausible strength of reversion rescues Steady Dip

Sweeping the positive control's reversion strength from none to implausibly strong — a 1.9-day
half-life with 60% of daily variance transient is far more reversion than a liquid index tracker
has ever shown — neither rule reaches the bar:

| half-life | transient share | Steady Dip mean gross | Deep Dip mean gross |
| --- | --- | --- | --- |
| none | 0% | −0.26% (−3.3×) | −0.21% (−2.6×) |
| 1.9d | 60% | +0.04% (0.5×) | **+0.34% (4.3×)** |
| 3.1d | 60% | −0.01% (−0.1×) | +0.30% (3.7×) |
| 6.6d | 60% | −0.06% (−0.8×) | +0.17% (2.1×) |
| 6.6d | 90% | +0.01% (0.1×) | +0.33% (4.1×) |
| 13.5d | 90% | −0.02% (−0.3×) | +0.18% (2.2×) |
| 34.3d | 95% | +0.00% (0.0×) | +0.08% (0.9×) |

Steady Dip peaks at 0.5× cost. Deep Dip peaks at 4.3×, against a bar of 10×.

Caveat worth keeping: this is one shape of reversion (AR(1) deviation from a drifting anchor). A
different shape — a sharp dislocation that snaps back in a day or two — could behave differently,
and is exactly what the real data would show.

### 5. Deep Dip is a strict subset of Steady Dip, so ADR 0024's separation claim is wrong

Across 1,542 Deep Dip entry days on three different processes, **every single one was also a
Steady Dip day. Zero exceptions.**

Once both carry the 50-day trend filter, a 20-day z-score at −1.5 that is still above its 50-day
average is always also below its 10-day average. They are not two signals. They are one rule at
two thresholds.

ADR 0024's "the overlap is negligible (3.2%)" was measured **before** the trend filter was added
to Deep Dip — it is in the table of the old, unfiltered Harvester, where nearly half the entries
were in downtrends that Steady Dip could never fire in. The ADR then decided to add the filter
and concluded, from the *pre-filter* overlap plus the new rarity, that "applying a trend filter
to both separates them completely". Rarity is not separation, and the overlap was never
recomputed.

ADR 0024's own figures already show it: 748 overlapping days before the filter, 605 Deep Dip days
after it. The filter removed almost exactly the days that were *not* shared.

This is the claim the ADR uses to justify keeping both strategies. It does not survive.

## The three questions

**1. Does the bounce exist at all?** — **Unanswered, and the existing evidence for it is void.**
No real prices were reachable. What is now established is that nothing in ADR 0021 or ADR 0024
was evidence of a bounce: the headline +0.26% is drift, the 70% win rate is exit geometry, and
the recovery rate barely moves between "no reversion" and "strong reversion". The assumption is
not merely untested — the numbers offered in its support are uninformative.

**2. Does the typical win clear ~10× costs?** — **No, and for Steady Dip this needs no data.**
Its frozen target averages less than the 0.80% it has to beat, so its ceiling under flawless
execution is the bar itself. Under every reversion strength tested it lands at 0–0.5×. Deep Dip
has the headroom (ceiling 16–21×) but reached only 4.3× at its best, with reversion far stronger
than is plausible.

**3. Is the win rate anywhere near the ~70% the design assumes?** — **Yes, and that is the
problem.** 68–70% is what a random walk with no reversion produces. The design's headline
assumption is satisfied by noise, so meeting it on real data would mean nothing. Win rate is the
wrong instrument here; mean gross against cost is the right one, and it is negative in every
control.

## The finding flagged as untrustworthy

> does the deeper Deep Dip entry actually beat the shallow Steady Dip entry, or was that just the
> simulator's own bias showing?

**It was the simulator.** The sign of the difference is a direct readout of the generator's
reversion parameter:

| control | reversion | Steady mean | Deep mean | Deep − Steady |
| --- | --- | --- | --- | --- |
| `null-zero` | none | +0.04% | −0.09% | **−0.13%** |
| `null-drift` | none | +0.26% | +0.07% | **−0.20%** |
| `reverting` | strong | +0.31% | +0.50% | **+0.19%** |

Turn reversion off and the deeper entry is *worse* than the shallow one. Turn it on and it is
better. ADR 0024's +0.95% vs +0.33% is not a measurement of the entries; it is a measurement of
how much reversion was put into the generator. The ADR was right to distrust it, and right that
it must not be acted on before real data.

One directional steer that does survive: of the two, **Deep Dip is the only one with room to
clear the bar.** Steady Dip's target is too small regardless. If real data does show reversion,
the survivor is the rare, deep entry — which is the opposite of the universe decision in
ADR 0021, where the shallow, frequent rule got the curated low-cost GBP list built specifically
for it.

## What this does and does not supersede

It does **not** supersede ADR 0021 or ADR 0024. The measurement they asked for has not happened,
and a control run is not a refutation of a claim about real markets.

What it does establish, and what should be recorded against them:

- The three quantitative supports for the reversion assumption (mean move, win rate, recovery
  rate) are individually uninformative — each is reproduced by a process with no reversion.
- Steady Dip's exit geometry cannot clear ADR 0019's cost floor at any win rate. This is
  independent of whether reversion exists and should be settled before any further work on it.
- ADR 0024's "the two strategies are meaningfully distinct" is contradicted by its own numbers.
  They are one rule at two thresholds.

## Next

1. **Get prices.** An environment with egress to Twelve Data or Yahoo, or a committed cache. One
   fetch unblocks the whole test; the harness runs unchanged.
2. **Run `--check-currency` first.** The GBP-vs-USD line check has never been done, and the
   universe doc is right that it is the dangerous one.
3. **Check finding 3 against real volatility before anything else.** If the real distance from
   close to 10-day average on these funds is under 0.80%, Steady Dip is finished on arithmetic
   and the real-data question narrows to Deep Dip alone.
4. **Then run the full test**, at `--lag 0` for comparability with the ADRs and `--lag 1` for
   what the runtime can actually do. About a quarter of Steady Dip signals go stale before a
   next-close fill in the controls.
