# 9. v1 strategy roster, strategy style, and two-tier research

## Status

Accepted

## Context

The spec published in GitHub issue #1 scoped v1 to a single concrete strategy (Low-Vol
Compounder), deliberately, to prove the pipeline end-to-end before investing in more. Once
that pipeline design was in hand, we walked through what else was worth hardcoding for v1 and
concluded a single strategy under-serves the actual goal: comparing strategies against each
other (via `Book`-level performance, see ADR 0010) is only meaningful once there's more than
one to compare.

We also discussed how "confidence" should differ across strategies, and where an LLM research
layer fits — both `Insight`-related decisions bundled into this ADR since they came out of the
same conversation and inform the same roster.

## Decision

### Roster

v1 ships five strategies, not one:

1. **Low-Vol Compounder** *(originally specced)* — buy low-volatility, large-cap/index
   holdings, hold for small consistent gains. Data: daily OHLC, realized volatility (rolling
   stdev of returns).
2. **Volatility Harvester** — buy on a pullback vs. an asset's own recent range, trim on a
   bounce back toward the mean, optionally add on further weakness (bounded by a max position
   size). Data: daily OHLC, RSI or z-score vs. a rolling mean, the position's own cost basis.
3. **Trend Follower** — enter on a moving-average crossover (e.g. 50/200 golden cross) or an
   N-day high breakout; exit on the reverse crossover or a trailing stop. Data: daily OHLC only.
4. **Volatility Breakout** — flag a multi-month low in Bollinger Band width / ATR (a volatility
   squeeze), enter on the first confirmed close outside the bands; exit on volatility
   normalization or a trailing stop. Data: daily OHLC, Bollinger Bands/ATR.
5. **Value/Quality Dip-Buyer** — screen for P/E (or P/B) meaningfully below the instrument's own
   N-year average, combined with a dividend-yield floor and a basic quality filter (positive
   earnings, reasonable debt/equity); holds longer than the Harvester, closer to the Compounder's
   horizon. Data: fundamentals (P/E, dividend yield, debt ratios) — `yfinance` already supplies
   these for free and slots into the existing market-data provider boundary, so this needs no
   new external dependency or testing seam.

### Strategy style

Each `Strategy` is tagged `trading` (Harvester, Trend Follower, Breakout — shorter hold,
technical, frequent exits) or `investment` (Compounder, Value/Quality Dip-Buyer — longer hold,
conviction-based). This is descriptive metadata read by the research tier and by how a `Book`'s
performance gets interpreted, not a behavioral gate enforced elsewhere in the system.

### Confidence, by signal type

Confidence is not one thing across a strategy's signals:

- **Entry signals are forecasts** and should never be treated as more certain than the data
  supports. Confidence for an entry should be calibrated from the backtest engine: bucket
  historical signals by strength (e.g. "RSI 20-25" vs "15-20"), use the realized win rate/
  expectancy in that bucket as the confidence for a live signal landing in the same bucket —
  not a hand-tuned "feels right" number.
- **Exit signals that realize a pre-calculated outcome are arithmetic, not forecasts** — "price
  hit the target/stop I calculated at entry, lock in the actual profit now." These are
  near-certain by construction and should read as high-confidence (this is why Compounder's
  sells felt "always high confidence" — they're this kind, almost exclusively).
- **Volatility Harvester's add-on-weakness action is always manual**, regardless of the
  strategy's `Approval mode` / confidence threshold — it's the one action in the v1 roster where
  being confidently wrong compounds fastest (doubling down on a bet that hasn't worked yet), so
  it never becomes eligible for auto-execution.

### Two-tier `Insight` research

- **Screening tier**: cheap, runs on every candidate a strategy surfaces — news/sentiment
  summary, flags anything alarming (earnings miss, litigation, restructuring). A free-tier model
  (e.g. Gemini's free tier) is sufficient; this is classification/summarization, not deep
  reasoning, and needs to be cheap enough to run unconditionally.
- **Research tier**: deeper, multi-source synthesis producing a written thesis — runs only on
  candidates that already cleared a strategy's quantitative screen, so call volume stays low by
  construction even with a stronger, pricier model. Worth spending more here because the
  decisions it informs are long-hold, real-money commitments (`investment`-style strategies
  lean on this tier the most) — for a single-user account the low volume keeps absolute cost
  small regardless of tier, so the real question is research quality, not affordability.
- v1 ships the screening tier only (free/cheap, low-risk to build first); the research tier is
  a near-term fast-follow once the screening tier and the rest of the pipeline are proven —
  tracked in `BACKLOG.md`, not blocking v1.
- Exact model/provider selection for each tier is deliberately left open here — pricing and
  free-tier terms move; pick at implementation time, not locked into this ADR.

## Consequences

- The published spec (issue #1) undersells the roster — needs an update to describe five
  strategies instead of one, or a fast-follow issue; the v1 test matrix and backtest-comparison
  UI both need to handle N strategies rather than assuming one.
- Only strategy 5 (Value/Quality Dip-Buyer) adds a new kind of input (fundamentals) — the other
  four stay within the price-data footprint already planned, keeping the first roster expansion
  cheap.
- Confidence calibration now depends on the backtest engine being able to bucket historical
  signals by strength and compute realized win rate per bucket — a capability the backtest
  engine needs regardless, but worth calling out as a concrete requirement, not just "run
  backtests."
