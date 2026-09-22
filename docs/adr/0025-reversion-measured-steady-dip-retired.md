# 25. Reversion measured on real prices: Steady Dip is retired, Deep Dip is blocked on execution timing

## Status

Accepted. Supersedes ADR 0021 and ADR 0024.

## Context

ADR 0021 designed the Low-Vol Compounder around an assumption it could not test — that
short-horizon reversion exists in GBP index trackers — and said so explicitly: *"It must be
measured on real data covering at least 2018-2025, including 2020 and 2022, before this ships.
If the reversion is not there, or does not survive a 0.08% cost, the honest outcome is that this
strategy should not exist."* ADR 0024 then built a second strategy on the same untested
assumption, and flagged its own comparison of the two entries as the least trustworthy number
in it.

That measurement has now run. Full report and method: `docs/reversion-test-findings.md`.
Harness, prices and runs: `docs/analysis/reversion-test/`.

**22 of 22 candidate tickers resolve, and every one is the sterling line.** 2018-01-02 to
2026-09-18, ~2,200 daily bars each. The GBP-versus-USD failure ADR 0021 was most worried about
did not happen: the check discriminates (VUSD.L, VWRD.L, CSPX.L and IWDA.L all report `USD`),
and no USD line is in the list. The 0.08% cost base the design rests on is intact.

Every number below is an **edge over random entry** into the same instrument in the same year,
with a 95% interval bootstrapped over whole blocks — not a raw forward return. The distinction
is the reason this ADR exists: a rising asset drifts +0.33% per 10 trading days after every kind
of day, so ADR 0021's +0.26% and ADR 0024's +0.56% were never evidence of a bounce. They were
drift, reported as one.

### Reversion exists, and the entry ADR 0021 chose cannot see it

| | edge over random entry, lag 0 | 95% CI | no-reversion control | strong-reversion control |
| --- | --- | --- | --- | --- |
| **Steady Dip** | +0.05% | [−0.04%, +0.15%] | +0.04% | +0.05% |
| **Deep Dip** | **+0.38%** | **[+0.16%, +0.59%]** | −0.16% | +0.24% |

Steady Dip scores what a random walk with no reversion in it scores, to within a basis point —
and scores the same on a process with strong reversion, which says the shallow entry cannot
detect reversion even when it is known to be present. Its target sits 0.45% from spot, close
enough that noise reaches it either way.

Deep Dip's edge is outside both nulls, larger than the positive control, and the only interval
in the exercise that excludes zero. It survives collapsing the correlated tickers (three S&P 500
lines, five world trackers) into 11 index groups, and resampling whole years only. It is
positive in 7 of 9 years and *rises* to +0.41% with 2020 and 2022 removed, so it is not a
rebound artefact.

The contrast by year is the decisive evidence. Steady Dip's full-sample +0.05% is +0.94% in 2020
netted against **−1.18% in 2022**; excluding 2020 it is −0.08%. In 2022 it took 689 entries at
−1.15% net each with a 47.2% win rate — a 50-day trend filter rolls over slowly enough that the
rule spends a bear market buying every dip in it.

### Neither rule clears ADR 0019's cost floor

Against the 10 × 0.08% = 0.80% bar:

| | mean gross | × cost | 95% CI | typical win | mean net |
| --- | --- | --- | --- | --- | --- |
| Steady, lag 0 | −0.03% | −0.4× | [−1.3×, +0.4×] | +0.39% (4.8×) | **−0.11%** |
| Steady, lag 1 | +0.08% | 1.0× | [−0.0×, +2.0×] | +0.56% (7.0×) | +0.00% |
| Deep, lag 0 | +0.52% | 6.5× | [+4.2×, +8.7×] | +1.19% (14.9×) | +0.44% |
| Deep, lag 1 | +0.33% | 4.1× | [+1.9×, +6.2×] | +0.83% (10.4×) | +0.25% |

Deep Dip's *typical win* clears the bar comfortably; its *expectancy* does not, and expectancy is
what ADR 0019 checks. Its interval tops out at 8.7×, so the shortfall is not a sampling question.

Steady Dip's is worse than a shortfall — it is a ceiling. Its frozen target averages **0.61%** on
real entry days, so the most it could earn if every entry hit its target and none ever lost is
**7.6× against a bar of 10×**. ADR 0019 set 10× as "a starting bar, tuned once there is real
data"; the data is here and the bar is doing its job. Nothing in the result argues for lowering
it to fit — Deep Dip at 4.1× executable is not a near miss.

### The win rate assumption was satisfied by noise, as suspected — but only for the shallow rule

Real Steady Dip wins 76.4% of trades while losing money gross (+0.39% wins against −1.50%
losses). The no-reversion controls give it 68–70%. The design's headline assumption is met and
means nothing.

For Deep Dip the same metric *is* informative: the nulls give it 54–57% against a real 74.7%. The
metric's usefulness scales with how far the target sits from spot, which is a better rule of
thumb than "win rate is the wrong instrument".

### The two strategies are one rule at two thresholds

Of 533 real Deep Dip days, **all 533 are also Steady Dip days — 100.0% overlap**, matching all
three controls. ADR 0024's "the overlap is negligible (3.2%)" was measured before the trend
filter was added to Deep Dip, and the filter removed precisely the days that were not shared. The
claim ADR 0024 uses to justify keeping both strategies does not hold on real prices.

ADR 0024's least-trusted finding — that the deeper entry beats the shallow one — is upheld in
direction: +0.33%, CI [+0.11%, +0.55%], the only row in that comparison whose interval excludes
zero. Its magnitude (+0.95% against +0.33%) was still the simulator.

### A blocker neither ADR anticipated: the edge is in the day we cannot trade

Measured at `--lag 1`, filling at the next close rather than the signal close:

| | lag 0 | lag 1 |
| --- | --- | --- |
| Deep Dip edge | +0.38% [+0.16%, +0.59%] | **+0.15% [−0.08%, +0.37%]** |
| Deep − Steady | +0.33% [+0.11%, +0.55%] | +0.07% [−0.14%, +0.28%] |

About 60% of the edge, and nearly all of the deep entry's advantage over the shallow one, lives
in the single day between the signal close and the next close. ADR 0002's runtime is a scheduled
pass, not a market-close execution, so `--lag 1` is what it can actually do and `--lag 0` is a
comparability convention for the ADRs' own numbers.

Separately, 25.4% of Steady Dip signals go stale before a next-close fill (the price is already
back at or above its 10-day average, leaving no trade); Deep Dip loses 4.2%.

## Decision

### Steady Dip is retired

It is not a tuning problem. The entry cannot detect reversion on a process built to contain it;
the frozen target is structurally too small to clear the cost floor even under flawless
execution; and the one year it looks good is cancelled by the one year it looks catastrophic.
ADR 0021 named this outcome in advance and it has arrived.

The `LowVolCompounder` slot in the roster is vacated rather than re-parameterised. Its
`Strategy config version` history does not carry forward — nothing measured against the old
design transfers to whatever fills the slot.

Rejected: widening the target, since the ceiling comes from the trend filter selecting shallow
dips, not from the target being set too tight. Rejected: dropping the 50-day filter to get deeper
entries, because that is Deep Dip, which already exists.

### Deep Dip is not promoted, and is blocked on one measurement

The edge is real and robust at lag 0. That is a genuine finding and the strategy is not retired
with its sibling. But it does not clear ADR 0019's floor at either lag, and at the executable lag
its edge is not distinguishable from zero.

Deep Dip stays at `manual` approval and is not promoted until the execution-timing question is
answered: **how close to the market close can a scheduled pass fill, and what does that do to the
+0.38% → +0.15% decay?** That is one measurement against the live venue, and it is worth more
than any parameter in the strategy. If a pass can fill near the close, Deep Dip has something and
the cost-floor conversation is worth having; if it cannot, Deep Dip is Steady Dip with a longer
wait.

No entry threshold, hold length or stop is set here. ADR 0024 deferred those to "one measurement
rather than two guesses", and setting them now would be fitting to a lag-0 number the runtime
cannot realise.

### The universe decision inverts

ADR 0021 gave the curated low-cost GBP tracker list to the shallow, frequent rule, on the
reasoning that many small trades make the cost base worth more than any parameter. The shallow,
frequent rule is the one with no edge. The surviving rule is the rare, deep one, which fires
1.1% of eligible days — about 60 entries a year across 22 instruments.

The cost base still matters, and the sterling-line validation above stands and should be kept.
But cost-per-trade is no longer the axis that selects the universe, because the surviving
strategy does not trade enough for it to dominate. The list's *breadth* now matters more than its
cheapness: at 1.1% of days, a 22-instrument universe is the difference between a working strategy
and one that fires too rarely to allocate to.

### ADR 0024's structural findings stand; its separation claim is withdrawn

The findings that did not depend on the reversion assumption survive unchanged: bounce targets
frozen at entry, Deep Dip carrying the same 50-day trend filter, the add gated behind it, exits
becoming partial, and exits owned by the enforcement layer (ADR 0018).

Withdrawn: "the two dip strategies both stay, as configurations of one implementation". They are
one rule at two thresholds and only one threshold has an edge. ADR 0023's shared-implementation
structure is unaffected — it now has one configuration rather than two.

## Consequences

- **The roster loses a strategy and gains no replacement.** With Steady Dip retired and Deep Dip
  unpromoted, the ADR 0009/0023 roster has one fewer working entry than it is written for. The
  remaining strategies' allocations under ADR 0020 need revisiting; the 25% of account value
  ADR 0021 reserved for the Compounder is unassigned.
- **Execution timing becomes a first-class concern.** It was previously an implementation detail
  of ADR 0002's scheduled pass. It is now the single measurement that decides whether the one
  strategy with a measured edge is viable. It needs its own spec and ticket.
- **ADR 0019's 10× floor is validated as a filter.** It rejected both rules, including one that
  looked good on every metric its designers checked. This is the first time it has been applied
  to real measured data and it behaved as intended. It should not be tuned down in response to
  the first strategies it rejects.
- **`TwelveDataSource` does not pass `outputsize`.** Twelve Data defaults it to 30 rows even with
  `start_date` and `end_date` set, so a multi-year request silently returns about a month. This
  run used Yahoo and avoided it. It affects any backtest on the primary provider and wants its own
  spec and ticket.
- **The candidate list is validated against Yahoo, not T212.** All 22 are the sterling line and
  all resolve. ADR 0021's requirement to validate against T212 instrument metadata — spreads and
  tradability on the venue that will actually fill these — is unchanged and still blocking.
- **Win rate should stop being a headline metric for any dip strategy**, unless reported next to
  the target distance that produced it. A 70% win rate with a 0.45% target is noise; the same
  rate with a 1.32% target is signal.
