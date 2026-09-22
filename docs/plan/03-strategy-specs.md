# 03 · Strategy specifications

Implement these exactly. Every default below came from a measured test (see `08-research-log.md`). Parameter **ranges** are the bounds the Settings UI enforces; they are not recommendations.

## Shared definitions

**Previous close rule.** Every *daily* indicator (SMA50, SMA200, 20-day z-score, market regime) is computed from completed daily closes up to and including the **previous** trading day. Today's live price never feeds today's daily indicators. This is what the research measured; breaking it introduces look-ahead bias.

**Market index (UK).** Equal-weighted index of the dip-strategy universe: each day, the mean of the daily returns of all universe instruments with a price that day; cumulative product starting at 1. `market_uptrend = index > SMA(index, 200)`.

**Market index (US).** SPY daily close vs its SMA200. Used only by the Crash-buyer for US stocks.

**z-score.** `z = (close − SMA(close, N)) / STDEV(close, N)` over the last N bars (sample standard deviation).

**Trading time.** Hold periods count **trading days** or **trading hours** using the exchange calendar (LSE for GBP ETFs, NYSE for US stocks), excluding weekends and holidays. Never calendar days.

**Fill.** Market order at the next available opportunity after the signal: next session's open for daily strategies; the start of the next hourly bar for the Compounder. Quantity is computed from a fresh price at submission (see `04-sizing-and-risk.md`).

**Exit levels.** On fill, store `target_price`, `stop_price`, `exit_by` on the position (per Book lot). The exit enforcer sells when `price ≥ target_price`, `price ≤ stop_price`, or `now ≥ exit_by`. Strategies may refresh `target_price` on their own open lots only.

**One position per instrument per strategy.** A strategy never holds two lots of the same instrument, and holds at most one instrument per instrument group (see `04-sizing-and-risk.md`).

**Universe (dip strategies).** Built automatically from T212 instrument metadata: type ETF, currency GBP or GBp, equity index or equity sector exposure, sufficient liquidity (hourly price data for most trading hours). Excluded: gold and other commodities, property, dividend-income funds, bonds, any USD/EUR-denominated line, and any instrument Aayan holds personally. See "Initial universe" at the end.

---

## 1. Deep Dip

**Idea.** A healthy equity ETF that closes unusually far below its recent average, while the market is healthy, tends to recover towards that average within days.

**Timeframe:** daily. **Evaluated:** once per trading day, before the LSE open, on the previous close. **Status:** Active (demo).

### Entry (all must be true, on the previous close)
1. `z20 = (close − SMA20) / STDEV20 ≤ −1.5`
2. `close > SMA50` (instrument's own trend intact)
3. `market_uptrend` (UK market index above its SMA200)
4. Instrument not currently held by Deep Dip; no other Deep Dip lot in the same instrument group

### Exit
- **Target:** SMA20. Written at entry as the previous close's SMA20; **refreshed each trading day** before the open by Deep Dip's scan. Typically ~+1.2% above entry.
- **Stop:** `entry × 0.90` (−10%). Catastrophe stop only; never fired in testing.
- **Time:** 20 trading days after entry.

### Parameters
| Name | Default | Range | Meaning | Raising it means |
|---|---|---|---|---|
| Dip lookback | 20 days | 10–60 | Window that defines "normal" price | Slower, fewer signals |
| Dip threshold | −1.5σ | −3.0 to −1.0 | How unusual the close must be | Closer to 0: more, shallower dips, weaker edge |
| Own-trend filter | 50-day SMA | 20–200 | Is this instrument still healthy? | Longer: stricter, fewer signals |
| Market filter | 200-day SMA | 100–250 | Is the market healthy? | Longer: slower to switch off in a fall |
| Target average | 20-day SMA | 10–50 | Where the bounce is considered complete | Longer: bigger, slower wins |
| Catastrophe stop | −10% | −20% to −5% | Tail-risk backstop | Closer to 0: more trades stopped before recovering |
| Max hold | 20 trading days | 5–30 | When the thesis is judged failed | Longer: ties up the slot; didn't improve results (R10) |

### Signal card "why it fired"
`Dip below 20-day average: −1.8σ (needs ≤ −1.5σ)`, `Above 50-day average: +x%`, `Market above 200-day average: +y%`.

### Evidence
8 years daily, 22 ETFs: net edge +0.38%/trade after cost at 5-day hold, CI excludes zero, 4.8× cost; with back-to-average exit: 82% win, avg +0.87%, 7.9 days, 3.6× index return per day held (R1, R5). **Open:** re-test on real open prices and on the ~37-ETF universe (Phase 1 research).

---

## 2. Compounder

**Idea.** The same bounce effect on hourly bars: frequent small wins from unusual intraday dips in liquid equity ETFs, only in a healthy market.

**Timeframe:** hourly. **Evaluated:** at the close of each hourly bar during the LSE session. **Status:** Active (demo).

### Entry (all must be true)
1. `z40h = (hourly close − mean of last 40 hourly closes) / stdev of last 40 hourly closes ≤ −2.5`
2. Instrument's previous daily close `> SMA50` (daily)
3. `market_uptrend` on the previous daily close
4. Not held by the Compounder; no other Compounder lot in the same group

### Exit
- **Target:** the 40-hour mean at the signal bar, **fixed at entry**. Typically ~+1.2% above entry (median 1.19%, IQR 0.85–1.72%).
- **Stop:** `entry × 0.95` (−5%). Never fired in testing; unverified.
- **Time:** 45 trading hours after entry (≈5 trading days).

### Parameters
| Name | Default | Range | Meaning | Raising it means |
|---|---|---|---|---|
| Lookback | 40 hours | 20–80 | "Normal" price over ~4–5 trading days | Slower, fewer signals |
| Dip threshold | −2.5σ | −3.5 to −1.5 | How unusual the hourly drop must be | Closer to 0: more trades but **edge falls below cost at −2.0** (R13) |
| Own-trend filter | 50-day SMA | 20–200 | As Deep Dip | As Deep Dip |
| Market filter | 200-day SMA | 100–250 | As Deep Dip | As Deep Dip |
| Catastrophe stop | −5% | −10% to −2% | Backstop | Closer to 0: more premature exits |
| Max hold | 45 trading hours | 9–90 | Time to bounce | 90h added only tail risk (R6) |

### Operational notes
- Signals go stale fast. Approval **expires at the end of the next hourly bar**. Plan for auto-approval once the first ~10 demo trades look right (Phase 2).
- ~340 signals/year on the ~42-instrument test universe; with 3 slots, expect ~150–250 actual trades/year.

### Evidence
2 years hourly (Nov 2023–Sep 2026). Liquid 7: edge 3.2× cost; 42 instruments: 344 signals/yr, edge +0.53%, CI [0.42, 0.64] (R4, R14). With back-to-average exit: 78% win, avg +0.54–0.77% (R6, R8). **Caveat:** mostly a rising market; demo record matters.

---

## 3. Crash-buyer

**Idea.** Diversified holdings that fall far below their long-term trend during a market-wide fall tend to recover over the following months.

**Timeframe:** daily. **Evaluated:** once per trading day before the relevant open (LSE for ETFs, NYSE for US stocks). **Status:** Active (demo), small allocation.

### Entry
**ETFs (dip-strategy universe):**
1. `close ≤ 0.92 × SMA200`
2. UK market index **below** its SMA200

**US large caps:**
1. `close ≤ 0.92 × SMA200`
2. SPY **below** its SMA200 (mandatory: dips in a rising market were value traps, R11)
3. `0 < P/E ≤ 25`, dividend yield `≥ 1.5%`, debt/equity `≤ 60`. **Any missing figure → skip.**
4. Single stock cap 5% of Loom budget.

Both: not held personally, not already held by the Crash-buyer, one per group.

### Exit
- **Target:** `entry × 1.10` (+10%), fixed.
- **Stop:** `entry × 0.85` (−15%). Gaps can exceed it; worst tested trade −25.5%.
- **Time:** 60 trading days.

### Parameters
| Name | Default | Range | Meaning |
|---|---|---|---|
| Dip depth | 8% below SMA200 | 5–20% | How broken things must be |
| Trend window | 200-day SMA | 100–250 | "Long-term trend" |
| Target | +10% | +5% to +25% | Recovery to take |
| Stop | −15% | −25% to −5% | Tighter stops fired mid-crash (R7) |
| Max hold | 60 trading days | 20–120 | 120 raised win rate, lowered return per day |
| Max P/E | 25 | 10–40 | US stocks only |
| Min dividend yield | 1.5% | 0–5% | US stocks only |
| Max debt/equity | 60 | 20–200 | US stocks only |

### Evidence
ETFs: 84% win, avg +6.0%, 5.3× index return per day; 43% of trades in 2020, ex-2020 avg still +8.6% (R7). US stocks: no statistically significant edge over random entry (R11). **Treat the US version as an experiment.** Priced in USD: ~0.35% round trip; currency moves affect GBP P/L.

---

## 4. Squeeze Breakout

**Idea.** After an unusually quiet period, the first strong move up tends to continue. Buys strength, unlike the other three.

**Timeframe:** daily. **Status:** **Shadow only** (signals tracked, no orders) until its sample is large enough.

### Entry (matches `volatility_breakout.py`)
1. Bollinger bands: 20-day SMA ± 2 × population stdev. `width = (upper − lower) / SMA20`.
2. Squeeze on the previous bar: `width ≤ 1.05 × min(width, last 60 days)` AND `width ≤ 0.5 × mean(width, last 60 days)`.
3. Breakout: close > previous bar's upper band.

### Exit
- **Stop:** `entry × 0.94` (−6%). A real stop: failed breakouts don't come back (removing it produced a −35% trade, R8b).
- **Volatility exit:** when `width ≥ 1.6 × squeeze-low width`, issued by the strategy's daily pass (not the exit enforcer). Sell at next open.
- **Time:** 45 trading days.

### Parameters
| Name | Default | Range |
|---|---|---|
| Band window / width | 20 days / 2σ | fixed |
| Squeeze lookback | 60 days | 40–120 |
| Squeeze tolerance | 1.05× low | 1.0–1.2 |
| Squeeze vs mean | 0.5× | 0.3–0.7 |
| Normalisation multiple | 1.6× | 1.2–2.5 |
| Stop | −6% | −10% to −3% |
| Max hold | 45 trading days | 20–60 |

### Evidence
76% win, avg +0.5%, 1.7× index return per day; weakest of the four; small sample (R8b).

---

## Initial universe (dip strategies)

Starting candidate list, all confirmed GBP/GBp on Yahoo in Sep 2026. **Claude Code should generate the live list from T212 metadata using the rules above, then compare against this list and report differences.**

VUSA, CSP1, VUAG, IUSA, SPXP, VNRT, IGUS, HMUS, EQQQ, IITU, SEMI, DGIT, VWRL, VWRP, SWLD, IWRD, HMWO, WLDS, IWFQ, IWFM, IWFV, ISF, VUKE, MIDD, VMID, VEVE, VERX, VEUR, VJPN, VAPX, EMIM, VFEM, HMCH, HMEF, INRG, IH2O, XMWX, FRXE, VNRG

Each must be checked against its factsheet to confirm it is an equity index or equity sector fund (the tickers were screened for currency and data quality, not fund type).

Excluded after testing or by rule: SGLN (gold), IUKP (property), IDVY, IUKD, VHYL, IAPD (dividend income), AGBP, IGLT, VGOV, VAGP (bonds), CUKS, EMV, HPRO, ISXF (too thinly traded), and USD lines (IUHC, RBOT, ECAR, HEAL, WTAI, VDPX, GLDV, XDWD).

Remove anything in Aayan's personal holdings (Manual book) at runtime.
