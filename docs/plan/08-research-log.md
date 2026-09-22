# 08 · Research log

All tests run on 22–23 Sep 2026. Read this before changing any rule; most "obvious improvements" have already been tested.

## R0. Method and data

- **Daily data:** 22 GBP ETFs, daily closes 2018-01 to 2026-09 (close only, no open/high/low). "Next open" entries were **approximated by next close**. Deep Dip must be re-tested on real open prices (Phase 1).
- **Hourly data:** Yahoo 60-minute bars, ~Nov 2023 to Sep 2026 (≈2.8 years), LSE ETFs; bars with zero volume dropped. Entries at the next bar (open where stated, otherwise next close).
- **US data:** 50 US large caps + SPY, daily adjusted closes 2010–2026. **Survivorship bias:** these are today's large companies; results for dip-buying are flattered.
- **Costs:** 0.08% round trip for GBP ETFs, 0.35% for US stocks.
- **Edge over random:** mean return of signal trades minus mean return of entries on all eligible bars in the same data. Two variants were used: (a) fixed holding horizon, (b) the same exit rules applied to random entries. Values from different variants are not directly comparable.
- **Confidence intervals:** block bootstrap, blocks = (instrument, year) for daily tests or (instrument, month) for hourly tests.
- **Return per day held vs holding:** total strategy return ÷ total days capital was deployed, compared with the average daily return of simply holding the same instruments. Measures capital efficiency.
- **Multiple testing:** many variants were tried; neighbouring configurations agreeing matters more than any single best number. Demo results are the final arbiter.

## Deep Dip

**R1. Regime filter (5-day hold, cost 0.08%).**
| Filter | n | Gross edge | 95% CI | Net ÷ cost |
|---|---|---|---|---|
| None | 5,045 | +0.14% | [+0.04, +0.24] | 0.7× |
| Own 50-day only | 496 | +0.32% | [+0.15, +0.47] | 3.0× |
| Market 200-day only | 2,734 | +0.24% | [+0.11, +0.37] | 2.0× |
| **Both** | **357** | **+0.46%** | **[+0.27, +0.64]** | **4.8×** |

2022 entries: own-only 87, market-only 128, both 4. Positive in 7 of 9 years. Market-only was worse than own-only: it admits instruments falling for their own reasons.

**R5. Exit rules (~200 trades, combined filter).**
| Exit | Win | Avg days | Return/day vs holding | Worst |
|---|---|---|---|---|
| 5 days fixed | 56% | 5.0 | 2.6× | −7.1% |
| 5 days + 3σ stop | 55% | 4.6 | 2.7× | −4.3% |
| 10 / 20 days fixed | 63% | 10 / 20 | 1.4× / 1.5× | |
| +1% target, max 20d | 78% | 8.6 | 2.3× | −7.8% |
| +2% target, max 60d | 78% | 25.5 | 0.5× | −37.3% |
| **Back to 20-day avg, max 20d** | **82%** | **7.9** | **3.6×** | **−4.3%** |
| 5 days, extend if losing, max 20d | 85% | 7.5 | 3.8× | −7.3% |
| Never sell below +1% | 97% | 57.4 | 0.6× | −26.4% |

The 3σ volatility stop fired on 33 of 206 trades (too often for an emergency stop) → replaced by a fixed −10% catastrophe stop. "Never sell at a loss": 11 trades stuck > 1 year, one 1,340 days, 6 never recovered by data end.

**R9. Fixed vs refreshed target (Deep Dip).** Refreshed daily: 82% win, 7.9 days, 3.6×. Fixed at entry: 77%, 11.3 days, 2.3×; 71 of 205 timed out. Median target distance above entry 1.22% (IQR 0.67–1.93%). → Refresh daily.

**R10a. Time-exit follow-up (Deep Dip).** 15 of 205 trades (7%) timed out, median −2.6% at exit. Back to breakeven within 20 more days: 47%; within 60: 67%; not within a year: 27%. Holding 20 / 60 more days: avg −2.1% / −1.9%, while the index gained ~0.6% / 1.8%. → Keep time exit.

**R12. Deep Dip on US large caps (0.35% cost).** 68 trades/yr, avg +0.42%, win 69%, edge +0.45% CI [+0.22, +0.67], but **0.9× SPY** return per day; avg win +2.4%, avg loss −4.0%, worst −18.6%. → Not used.

## Momentum

**R2. 12-1 month momentum, top 4 of 22, monthly (2019–2026).** Ann. return 7.8%, Sharpe 0.66, max DD −15.1%. With absolute momentum (gilts when negative): 7.5%, 0.62, −15.7%. Equal-weight all 22, held: 8.4%, **0.85**, −15.6%. → Dropped. The universe lacks cross-sectional dispersion (all broad equity trackers).

## Compounder (hourly)

**R3. Intraday reversion without filter (18 equity ETFs, fixed-horizon edge).** Best: 20h lookback, −2.5σ, 9h hold: edge +0.073% CI [+0.01, +0.14], 0.9× cost. 40h/−2.5σ/18h: +0.126% CI [−0.003, +0.26]. Typical absolute hourly move 0.11%. → Real effect, about equal to cost.

**R4. With regime filter; liquid 7 (VUSA, CSP1, VUAG, VWRL, VWRP, SWLD, ISF).**
| Universe | Config | Signal bars | Edge | 95% CI | ÷ cost |
|---|---|---|---|---|---|
| Liquid 7 | 40h / −2.5σ / 18h | 423 | +0.26% | [+0.10, +0.42] | 3.2× |
| Liquid 7 | 20h / −2.5σ / 9h | 382 | +0.18% | [+0.10, +0.25] | 2.3× |
| 18 equity | 40h / −2.5σ / 18h | 1,174 | +0.21% | [+0.11, +0.31] | 2.6× |
Without filter the same configs were 0.9–1.8×. (Signal bars ≠ trades: a dip can trigger on several consecutive hours.)

**R6. Exit rules (liquid 7, 40h/−2.5σ, regime).**
| Exit | Win | Avg hold | Return/hour vs holding | Worst |
|---|---|---|---|---|
| 18h fixed | 61% | 18h | 2.3× | −2.2% |
| 36h fixed | 69% | 36h | 1.1× | −3.3% |
| **Back to 40h avg, max 45h** | **78%** | **22h** | **2.6×** | **−3.2%** |
| Back to avg, max 90h | 78% | 23h | 2.6× | −10.2% |
| 18h, extend if losing, max 45h | 86% | 25h | 2.1× | −3.2% |
The −5% stop never fired.

**R8. Fixed vs moving target (Compounder).** Moving: +0.54%/trade, 22h, 2.6×. **Fixed at entry: +0.77%, 32h, 2.5×.** Fixed +0.3/0.5/0.75% targets: 2.1× / 1.8× / 1.7×. Target distance median 1.19% (IQR 0.85–1.72%). → Fixed at entry.

**R10b. Time-exit follow-up (Compounder).** 66 of 163 trades (40%) timed out, median return at exit 0.0% (scratch trades). Back above breakeven within 9h: 50%, within 45h: 77%. Holding 45 more hours: avg −0.08%. → Keep time exit.

**R13. Trade counts (non-overlapping trades/yr).**
| Setting | Trades/yr | Avg per trade |
|---|---|---|
| Liquid 7, −2.5σ | 63 | +0.77% |
| 18 equity, −2.5σ | 160 | +0.54% |
| Liquid 7, −2.0σ | 90 | +0.43% |
| 18 equity, −2.0σ | 236 | +0.33% |
Loosening to −2.0σ drops the fixed-horizon edge below cost (R3: 40h/−2.0σ/9h regime ≈ 0.93×). → Grow trades by widening the universe, not by loosening the trigger.

**R14. Wider GBP universe (same-exit-rules edge).**
| Universe | Instruments | Trades/yr | Avg | Edge | 95% CI |
|---|---|---|---|---|---|
| Liquid 7 | 7 | 66 | +0.80% | +0.76% | [+0.60, +0.95] |
| Original 18 equity | 18 | 165 | +0.60% | +0.56% | [+0.43, +0.69] |
| New GBP ETFs only | 24 | 179 | +0.54% | +0.50% | [+0.32, +0.69] |
| **All 42** | **42** | **344** | **+0.57%** | **+0.53%** | **[+0.42, +0.64]** |
Weak per instrument (small samples): SGLN (gold) −0.5%, IH2O −0.2%, WLDS, IDVY, IUKP ≈ 0. Strong: US/Nasdaq/tech/semis/world/Europe/EM. USD-priced LSE lines found and excluded: IUHC, RBOT, ECAR, HEAL, WTAI, VDPX, GLDV, XDWD. Thin (excluded): CUKS, EMV, HPRO, ISXF.

## Crash-buyer

**R7. Exit rules (18 equity ETFs, close ≤ 0.92 × SMA200).**
| Exit | Trades | Win | Avg | Return/day vs holding | Worst |
|---|---|---|---|---|---|
| +10% / −6% / 60d (old) | 142 | 68% | +4.0% | 5.2× | −13.1% |
| +10% / no stop / 60d | 84 | 83% | +6.0% | 4.3× | −18.4% |
| **+10% / −15% / 60d** | **101** | **84%** | **+6.0%** | **5.3×** | **−25.5%** |
| +10% / −15% / 120d | 90 | 90% | +7.2% | 4.8× | −25.5% |
| Back to SMA200 / −15% / 120d | 77 | 88% | +7.4% | 4.5× | −25.5% |
Old −6% stop fired on 40 of 142 trades (stopped out mid-crash, then re-bought lower). Inverted market filter: 136 vs 142 trades, same results. 2020 = 43% of trades; ex-2020 avg +8.6%.

**R11. US large caps, +10/−15/60d, 0.35% cost, vs random entry with same exits.**
| Condition | Trades | Avg | Win | Random | Edge | 95% CI |
|---|---|---|---|---|---|---|
| Any 8% dip | 1,089 | +2.9% | 68% | +2.5% | +0.46% | [−0.18, +1.12] |
| SPY below 200-day | 701 | +3.1% | 70% | +2.5% | +0.59% | [−0.25, +1.44] |
| SPY above 200-day | 584 | +1.5% | 62% | +2.5% | −0.94% | [−1.90, +0.11] |
Dips while SPY rises behave as value traps (worst: CVX, GE, NVDA, ADBE, MMM). → US version allowed only with SPY-below filter, as an unproven experiment.

## Squeeze Breakout

**R8b. Exit rules (daily).**
| Exit | Win | Avg hold | Return/day vs holding | Worst |
|---|---|---|---|---|
| **−6% / 45d / normalisation (current)** | **76%** | **9.7d** | **1.7×** | **−5.7%** |
| −6% / 45d, no normalisation | 73% | 41d | 1.4× | −8.9% |
| 45d fixed, no stop | 74% | 45d | 1.3× | −34.8% |
| Trailing 5% / 8% / 10% | 58–68% | 47–85d | 1.1–1.2× | −7 to −12% |
→ Keep current exits. Earlier evidence: positive at 45–60 day horizons but only ~230 entries in 8 years.

## Portfolio-level

**R11b. Deep Dip vs Compounder overlap (liquid 7, Nov 2023–Sep 2026).** 38 Deep Dip and 163 Compounder trades. Compounder entries while Deep Dip holds the same instrument: 12%; any of the 7: 17%. Deep Dip signals preceded by a Compounder entry on the same instrument within 3 days: 50%. Overlapping Compounder trades avg +1.29% vs +0.70% otherwise. Daily P/L correlation on shared days 0.56. Max concurrent positions 12. → Keep separate; the concentration risk is instrument groups, handled by group caps.

## Rejected ideas (and why)

| Idea | Why rejected |
|---|---|
| Old Low-Vol Compounder (calm names, hold for drift) | Its successor Steady Dip showed edge indistinguishable from zero against a positive control |
| Trend Follower / MA crossover | Negative in 9 of 9 years on this universe |
| Momentum rotation | R2 |
| Looser Compounder trigger | R13 |
| No stops / never sell at a loss on dip strategies | R5, R10 |
| Trailing stops on Squeeze | R8b |
| US stocks in Deep Dip / Compounder | R12; FX cost |
| UK single stocks | 0.5% stamp duty |
| Leveraged ETPs | Not available via T212 API/ISA |
| AI output as a trading input | Not measurable; D6 |

## Open research

1. Deep Dip on real open prices and the full ~37–42 ETF universe.
2. Intraday entry timing for Deep Dip (hourly check on dip days).
3. VIX (Yahoo `^VIX`) as a Crash-buyer trigger.
4. Economic-calendar filter (avoid entries before rate decisions / CPI).
5. Squeeze Breakout sample size.
6. Real spreads on less-liquid sector ETFs (from demo fee reconciliation).
