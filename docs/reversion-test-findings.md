# Does short-horizon reversion exist? — test findings

Status: **the test ran against real prices.** 22 of 22 candidate tickers resolved on Yahoo,
2018-01-02 to 2026-09-18, ~2,200 daily bars each. This is the measurement ADR 0021 asked for.

Harness: `docs/analysis/reversion-test/`. Prices: `docs/analysis/reversion-test/prices/`.
Runs: `docs/analysis/reversion-test/out/` (`real-lag0.txt`, `real-lag1.txt`, the three controls,
and the supplementary `trade-economics.txt` / `block-sensitivity.txt`).

**The short answer.** The bounce is real, but only at the deep entry, and only if you can trade
the close that produced the signal. Steady Dip has no measurable edge over random entry on any
cut of the data — its number is indistinguishable from a process with no reversion in it at all.
Deep Dip's edge is real and survives every robustness check at `--lag 0`, but it is not
distinguishable from zero once the fill moves to the next close, which is what the ADR 0002
runtime can actually do. Neither rule clears ADR 0019's 10× cost floor.

## 1. The universe resolves, and every line is sterling

All 22 candidates resolved. Four launched after the 2018 start and have shorter histories
(VUAG.L 2019-05-14, SWLD.L 2019-02-26, VAGP.L 2019-06-18, VWRP.L 2019-07-25); the rest run the
full 2,200 bars. Bar counts are ~253/year, so these are years, not the 30-row truncation the
primary provider would have produced.

**No USD line got in.** Every ticker reports `GBp` or `GBP`. The mix of the two is a Yahoo
labelling artefact — pence versus pounds — not two instruments: CSP1.L quotes at 61,528 (pence)
and VUSA.L at 108.03 (pounds), both sterling. Every measure here is a return, so the quote unit
cancels.

This is a real negative, not a default. The USD lines of these same funds were probed
deliberately and all report `USD`:

| GBP line (in the universe) | USD line (not in the universe) |
| --- | --- |
| VUSA.L → `GBP` | VUSD.L → `USD` |
| VWRL.L → `GBP` | VWRD.L → `USD` |
| CSP1.L → `GBp` | CSPX.L → `USD` |
| ISF.L → `GBp` | IWDA.L → `USD` |

So `docs/compounder-universe-candidates.md`'s dangerous failure did not happen — the ticker
column picked the sterling line in all 22 cases, and the 0.15%-each-way FX cost is not
silently reinstated. The 0.08% round trip the whole design rests on is intact.

## 2. Real volatility, and what it does to finding 3

Realised annualised volatility against the values the null-control generator assumed:

| bucket | assumed | real (range) | verdict |
| --- | --- | --- | --- |
| core | 15% | 14.7–20.3% | right neighbourhood |
| uk | 16% | 15.5–16.9% | right |
| regional | 17% | 16.1–18.5% | right |
| income | 16% | 13.4–18.0% | right |
| bond | 6% | **4.1–10.4%** | gilts understated by ~60% |

Equities average 16.6%, slightly *above* the 15% assumed. The gilt funds (IGLT 9.4%, VGOV 10.4%)
run far hotter than the 6% assumed; the hedged global aggregates (4.1%, 4.5%) run cooler.

**Finding 3 survives — but not for the reason it gave.** The quantity that matters is the frozen
target distance on the days Steady Dip actually fires. On real prices, at `--lag 0`:

| | mean target | median | ceiling vs the 0.80% bar |
| --- | --- | --- | --- |
| Steady Dip — real | **+0.61%** | +0.45% | **7.6×** |
| Steady Dip — `null-drift` | +0.80% | +0.61% | 10.0× |
| Steady Dip — `reverting` | +0.56% | +0.42% | 7.0× |
| Deep Dip — real | +1.41% | +1.32% | 17.6× |

Real lands at 0.61%, inside finding 3's quoted 0.56–0.80% band and near its bottom. The ceiling
on Steady Dip's mean gross trade — what it would earn if every entry hit its target and none ever
lost — is **7.6× cost against a bar of 10×**. Confirmed.

The mechanism, though, is not volatility. Finding 3 said "the whole finding scales with it", and
that is wrong. Across all days below the 10-day average with **no** trend filter, the real mean
gap is 1.16% (1.29% equities only) — comfortably over the bar. It is the `close > 50d avg`
condition that drags it to 0.61%, because requiring the price to still be above its 50-day
average systematically selects the shallow dips. So the trap is structural: **the trend filter
and the frozen target fight each other**, and raising volatility does not get Steady Dip out,
because a more volatile instrument that is still above its 50-day average is still only a little
below its 10-day one.

One consequence worth noting: at `--lag 1` Steady Dip's mean target *rises* to +0.86% (ceiling
10.8×), because waiting one day discards the shallowest dips — 8,069 entries fall to 6,020, so
**25.4% of Steady Dip signals go stale before a next-close fill**. Deep Dip loses 4.2%
(530 → 508). The lag improves the shape of Steady Dip's surviving trades and still does not make
it profitable.

## 3. Does the bounce exist?

The random-entry baseline on real prices: **+0.33% per 10 trading days**, 58.4% win rate, across
45,714 eligible days. That is the number any entry rule has to beat.

### Steady Dip: no.

| source | reversion | edge over random entry | 95% CI |
| --- | --- | --- | --- |
| **real, lag 0** | ? | **+0.05%** | [−0.04%, +0.15%] |
| `null-drift` | none | +0.04% | [−0.08%, +0.14%] |
| `null-zero` | none | +0.03% | [−0.10%, +0.15%] |
| `reverting` | strong | +0.05% | [−0.03%, +0.12%] |
| **real, lag 1** | ? | **+0.08%** | [−0.02%, +0.19%] |

Real Steady Dip is +0.05%. A random walk with no reversion whatsoever gives +0.04%. The interval
contains zero. This is not a weak positive — it is the null, reproduced to within a basis point.

Note the last row of the control column: the *positive* control also scores +0.05%. Steady Dip
scores the same on a process with strong reversion as on one with none, which says the shallow
entry cannot detect reversion even when it is definitely there. The rule is not measuring what it
was designed to measure.

### Deep Dip: yes at lag 0, and it is the only real result here.

| source | reversion | edge | 95% CI |
| --- | --- | --- | --- |
| **real, lag 0** | ? | **+0.38%** | **[+0.16%, +0.59%]** |
| `null-drift` | none | −0.16% | [−0.52%, +0.12%] |
| `null-zero` | none | −0.10% | [−0.51%, +0.18%] |
| `reverting` | strong | +0.24% | [−0.07%, +0.47%] |
| **real, lag 1** | ? | **+0.15%** | [−0.08%, +0.37%] |

+0.38% is outside both nulls, and *larger* than the strong-reversion positive control. It is the
only edge in the whole exercise whose interval excludes zero.

It excludes zero robustly. The 22 tickers are not 22 independent series — three S&P 500 lines,
five world trackers, two FTSE 250 lines, two gilt funds — so an (instrument, year) block
overstates precision. Collapsing the duplicate index lines into 11 groups, and then resampling
whole years only (9 blocks), barely moves it:

| blocking scheme | blocks | Deep Dip lag 0 | Steady Dip lag 0 |
| --- | --- | --- | --- |
| (instrument, year) | 194 | [+0.16%, +0.59%] | [−0.04%, +0.15%] |
| (index group, year) | 99 | [+0.05%, +0.68%] | [−0.10%, +0.20%] |
| year only | 9 | [+0.07%, +0.69%] | [−0.28%, +0.37%] |

Deep Dip stays clear of zero under all three; Steady Dip never approaches it.

**But `--lag 1` kills it.** +0.38% falls to +0.15%, and the interval covers zero under every
blocking scheme. Roughly 60% of the edge lives in the single day between the signal close and the
next close. That gap is the whole finding's fragility: ADR 0002's runtime is a scheduled pass,
not a market-close execution, so `--lag 1` is the honest convention and `--lag 0` is a
comparability convention for the ADRs' own numbers.

### By year

Edge over random entry, `--lag 0`. 2020 and 2022 shown in place:

| year | Steady n | Steady edge | Steady net | Deep n | Deep edge | Deep net |
| --- | --- | --- | --- | --- | --- | --- |
| 2018 | 403 | +0.17% | −0.13% | 38 | +0.86% | +0.54% |
| 2019 | 870 | −0.05% | +0.10% | 44 | +0.53% | +0.96% |
| **2020** | 1,064 | **+0.94%** | +0.28% | 29 | **+1.07%** | +0.80% |
| 2021 | 1,052 | −0.05% | −0.10% | 87 | +0.91% | +0.81% |
| **2022** | 689 | **−1.18%** | **−1.15%** | 92 | **+0.21%** | −0.20% |
| 2023 | 895 | −0.43% | −0.27% | 40 | −0.71% | +0.72% |
| 2024 | 1,176 | −0.09% | −0.16% | 126 | +0.28% | +0.22% |
| 2025 | 1,179 | +0.26% | +0.12% | 48 | +0.65% | +0.92% |
| 2026 | 741 | +0.11% | −0.06% | 26 | −0.31% | −0.18% |

The two years ADR 0021 insisted on are the two that decide it.

**Steady Dip is a 2020 artefact cancelled by a 2022 disaster.** Its full-sample +0.05% is
+0.94% in 2020 netted against −1.18% in 2022. Drop either and the number moves more than the
number itself:

| | edge | n |
| --- | --- | --- |
| full sample | +0.05% | 8,069 |
| excluding 2020 | **−0.08%** | 7,005 |
| excluding 2022 | +0.14% | 7,380 |
| excluding both | +0.01% | 6,316 |

It is positive in 4 of 9 years. 2022 is the year the design fails on its own terms: 689 entries
at −1.15% net each, a 47.2% win rate against its assumed 70%, and a 41.9% recovery rate. A
50-day trend filter rolls over slowly enough that the rule spends a bear market buying every dip
in it — which is exactly the failure ADR 0021 wrote the wide stop for, showing up in the entry
rather than the exit.

**Deep Dip is not a crisis artefact.** Its edge is positive in 7 of 9 years, and removing the two
extreme years *raises* it:

| | edge | n |
| --- | --- | --- |
| full sample | +0.38% | 530 |
| excluding 2020 | +0.34% | 501 |
| excluding 2022 | +0.46% | 438 |
| excluding both | **+0.41%** | 409 |

2020 contributes 29 entries out of 530 — it cannot be carrying the result. This is the strongest
thing in the report: whatever Deep Dip is picking up, it is not one rebound.

## 4. Does the typical win clear ~10× the 0.08% round trip?

The bar is 0.80%. Two different questions hide in this one, and they answer differently.

| | mean gross | × cost | 95% CI | typical **win** | × | typical **loss** | mean net |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Steady, lag 0 | −0.03% | −0.4× | [−1.3×, +0.4×] | +0.39% | 4.8× | −1.50% | **−0.11%** |
| Steady, lag 1 | +0.08% | 1.0× | [−0.0×, +2.0×] | +0.56% | 7.0× | −1.52% | **+0.00%** |
| Deep, lag 0 | +0.52% | 6.5× | [+4.2×, +8.7×] | +1.19% | **14.9×** | −0.99% | +0.44% |
| Deep, lag 1 | +0.33% | 4.1× | [+1.9×, +6.2×] | +0.83% | **10.4×** | −1.53% | +0.25% |

**The typical win clears 10× for Deep Dip and not for Steady Dip.** Deep Dip's median winning
trade is 14.9× cost at lag 0 and still 10.4× at lag 1. Steady Dip's is 4.8× / 7.0× — its wins are
too small to pay for themselves at the rate its losses arrive.

**Expectancy clears it for neither**, and expectancy is what ADR 0019's floor is about: it checks
"expected win per trade", not the size of the winners. Deep Dip's mean gross is 6.5× at lag 0
with a CI topping out at 8.7×, so the shortfall against 10× is not a sampling question — it is
below the bar, and at the executable lag it is 4.1×. Steady Dip's mean gross is *negative* gross
of costs at lag 0 and exactly break-even net at lag 1.

Steady Dip's asymmetry is the whole story: it wins +0.39% and loses −1.50%, a 3.8:1 loss-to-win
ratio that a 76% win rate does not cover.

ADR 0019 set 10× as "a starting bar, tuned once there is real data". There is now real data, and
the bar is doing its job: it rejects both rules. Whether 10× is the right number is a separate
decision, but nothing here argues for lowering it to fit — Deep Dip at 4.1× net-of-nothing is not
a near miss.

## 5. Is the win rate near 70%, and does it mean anything?

Yes, and it depends which rule you ask about — which is a refinement of what the controls alone
suggested.

| | real win rate (gross/net) | `null-drift` | `null-zero` | `reverting` |
| --- | --- | --- | --- | --- |
| Steady, lag 0 | **76.4% / 66.6%** | 70.1% | 68.1% | 75.3% |
| Steady, lag 1 | 75.1% / 69.2% | — | — | — |
| Deep, lag 0 | **74.7% / 73.0%** | **57.0%** | **54.4%** | 67.0% |
| Deep, lag 1 | 75.8% / 74.2% | — | — | — |

**For Steady Dip the win rate is meaningless, exactly as the controls predicted.** 68–70% is what
a driftless random walk produces. Real data gives 76.4% — and a *negative* mean gross trade. The
design's headline assumption is comfortably met while the strategy loses money, which is the
clearest possible demonstration that it was never the right instrument. High win rate, negative
expectancy: +0.39% wins, −1.50% losses.

**For Deep Dip the win rate is informative**, and this is a correction to finding 2 as previously
written. The nulls give Deep Dip 54–57%, not 68–70%. Real gives 74.7%, well outside. The
difference is target distance: Steady Dip's frozen target sits 0.45% away, close enough that
noise reaches it whether or not anything is reverting; Deep Dip's sits 1.32% away, far enough
that noise mostly does not. So "70% win rate" is uninformative for the shallow entry and
genuinely informative for the deep one — the metric's usefulness scales with how far the target
is from spot.

The recovery-rate metric the test was originally framed around remains the weak discriminator
finding 2 said it was. Real Steady Dip recovers to its 10-day average on a close 71.4% of the
time; `null-drift` gives 65.4% and `reverting` 70.9%. Real sits between two processes with
opposite amounts of reversion in them.

## 6. Does Deep Dip's deeper entry actually beat Steady Dip's shallow one?

**At lag 0, yes — and this is the one finding that flipped.** The controls showed the sign of the
difference tracking the generator's reversion parameter, which is why ADR 0024's version of it
was untrustworthy. Real data now sits outside that calibration:

| source | reversion | Steady mean | Deep mean | Deep − Steady | 95% CI |
| --- | --- | --- | --- | --- | --- |
| `null-zero` | none | +0.04% | −0.09% | −0.13% | [−0.42%, +0.19%] |
| `null-drift` | none | +0.26% | +0.07% | −0.20% | [−0.47%, +0.09%] |
| `reverting` | strong | +0.31% | +0.50% | +0.19% | [−0.08%, +0.45%] |
| **real, lag 0** | ? | +0.38% | +0.71% | **+0.33%** | **[+0.11%, +0.55%]** |
| **real, lag 1** | ? | +0.41% | +0.48% | +0.07% | [−0.14%, +0.28%] |

(The interval resamples both rules on the same (instrument, year) blocks, so the two are compared
on the same resampled data rather than independently.)

Real at lag 0 is the only row whose interval excludes zero — including the strong-reversion
control, whose +0.19% does not reach significance on this sample size. The deeper entry
genuinely is the better signal, and the direction ADR 0024 guessed was right even though its
evidence was not.

**At lag 1 the separation collapses to +0.07% and the interval covers zero.** The advantage of
the deep entry is, like the edge itself, concentrated in the day you cannot trade.

## 7. Finding 5 confirmed on real prices: they are one rule at two thresholds

| source | steady days | deep days | both | overlap |
| --- | --- | --- | --- | --- |
| real | 8,128 | 533 | **533** | **100.0%** |

Every one of the 533 real Deep Dip days is also a Steady Dip day. Zero exceptions, on real
prices, exactly as on all three synthetic processes. Deep Dip is 15.2× rarer than Steady Dip.

ADR 0024's "the overlap is negligible (3.2%)" is refuted on real data, not merely on controls. It
was measured before the trend filter was added to Deep Dip, and the filter removed precisely the
days that were not shared. The claim that the two strategies are meaningfully distinct — the
claim ADR 0024 uses to justify keeping both — does not hold.

## The three questions, answered

**1. Does the bounce exist?** — **Only at the deep entry, and only at the close that signalled
it.** Steady Dip's edge over random entry is +0.05% [−0.04%, +0.15%], numerically identical to a
random walk with no reversion and to a process with strong reversion alike. Deep Dip's is +0.38%
[+0.16%, +0.59%] at lag 0, outside both nulls and above the positive control, robust to
collapsing correlated tickers and to resampling whole years, and not a 2020 artefact. At lag 1 it
is +0.15% [−0.08%, +0.37%] — not distinguishable from zero.

**2. Does the typical win clear ~10× costs?** — **The typical win does, for Deep Dip only;
expectancy does not, for either.** Deep Dip's median winner is 14.9× cost (10.4× at lag 1), but
its mean gross trade is 6.5× (4.1× at lag 1) against a 10× bar, with the interval topping out at
8.7×. Steady Dip's median winner is 4.8× and its mean gross trade is negative. Finding 3's
arithmetic holds: Steady Dip's frozen target averages 0.61%, so its ceiling under flawless
execution is 7.6× — below the bar it has to clear.

**3. Is the win rate near 70%?** — **Yes: 74.7–76.4%. For Steady Dip that confirms nothing, for
Deep Dip it does.** The nulls give Steady Dip 68–70% with no reversion at all, and real data
gives it 76.4% alongside a negative mean gross trade. But the nulls give *Deep Dip* only 54–57%,
so its 74.7% is a genuine signal. The metric is only as informative as the target is far from
spot.

## What this supersedes

Superseded by **ADR 0025**, which records the decision. In summary:

- **ADR 0021's reversion assumption is half-refuted.** Short-horizon reversion does exist in this
  universe, measurably, in 2018–2026 real prices. It is not detectable by the entry ADR 0021
  chose. The strategy ADR 0021 designed — shallow dip, frozen 10-day-average target, GBP tracker
  list — has no edge over buying the same instruments on random days, and cannot clear ADR 0019's
  cost floor even in principle.
- **ADR 0024's separation claim is refuted on real data.** 100% overlap, not 3.2%.
- **ADR 0024's least-trusted finding is upheld in direction.** The deeper entry really is the
  better signal (+0.33%, CI excluding zero) — but only at lag 0, and the magnitude it reported
  (+0.95% vs +0.33%) was still the simulator.
- **A new blocker neither ADR anticipated.** The edge lives in the day between signal and
  next-close fill. Under ADR 0002's scheduled-pass runtime, most of it is unreachable. This is
  now the decisive question for Deep Dip, ahead of any parameter.

## Still outstanding

- **`TwelveDataSource` does not pass `outputsize`.** Twelve Data defaults it to 30 rows even with
  `start_date` and `end_date` set, so a multi-year request silently returns about a month. This
  run used Yahoo and did not hit it, but it affects any backtest on the primary provider and
  still wants its own spec and ticket.
- **The candidate list is validated against Yahoo, not T212.** All 22 are the sterling line and
  all resolve, but ADR 0021 asks for validation against T212's instrument metadata — spreads and
  tradability on the actual venue. That is still the instrument-sync work.
- **Execution timing is unmeasured.** How close to the close a scheduled pass can fill, and what
  that does to the +0.38% → +0.15% decay, is the measurement that decides whether Deep Dip has
  anything left.
