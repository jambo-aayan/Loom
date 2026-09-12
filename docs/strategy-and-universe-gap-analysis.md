# Strategy & Universe Gap Analysis

Audit of the v1 strategy roster (ADR-0009) and the instrument universe, ahead of designing
per-strategy logic. Findings are grouped by area; each is marked:

- **BLOCKING** — something that cannot work at all today
- **WRONG** — produces incorrect numbers or behaviour
- **GAP** — missing capability we've decided we want

Evidence for the empirical claims is reproducible via the fixture market-data source; the
per-strategy trade statistics come from a 2019-2024 backtest over the 4-instrument universe.

---

## A. Universe

The universe is the single biggest constraint on everything else, and it is barely modelled.

### A1. GAP — The universe is a hardcoded list, in three places

`DEFAULT_UNIVERSE` in `loom/api/routers/trading.py:23`, repeated as a literal in
`loom/cli/main.py:63` and `:110`, and again as `FixtureMarketDataSource.universe()`. There is no
universe table, no API, no UI, and no per-environment universe. Adding an instrument means
editing Python in three places and redeploying.

### A2. WRONG — The fixture source can silently supply synthetic prices in production

`loom/api/routers/trading.py:46` resolves the universe by duck-typing:
`getattr(source, "universe", lambda: DEFAULT_UNIVERSE)()`. Only `FixtureMarketDataSource`
defines `universe()`. And `get_market_data_source()` (`loom/api/deps.py`) falls back to
`FixtureMarketDataSource` whenever `twelve_data_api_key` is unset.

So if the Twelve Data key is missing, expired, or quota-exhausted at startup, the deployed app
trades against **seeded synthetic GBM prices** and nothing anywhere says so. The `universe()`
duck-type makes it worse: the fallback path is the only one that supplies its own universe, so
the substitution is invisible from the signal side too.

`MarketDataSource` should declare `universe()` on the base class so this is a type error rather
than a silent behavioural swap.

### A3. GAP — T212 ticker mapping is a static 4-entry dict

`loom/execution/t212_tickers.py` maps Loom tickers to T212's own namespace by hand. The module
docstring is honest that this is deliberate at 4 instruments. It does not survive universe
expansion: every new instrument needs a hand-verified entry, and a missing one raises
`UnmappedInstrumentError`.

### A4. BLOCKING — The `Manual` book cannot work

`Trading212Client.get_positions()` (`loom/execution/t212_client.py:168`) calls
`from_t212(row["instrument"]["ticker"])` with **no exception handling**, and `from_t212` raises
on any unmapped ticker.

CONTEXT.md promises the opposite:

> anything found in the real account that isn't tagged to a `Strategy`'s `Book` (including
> pre-existing Trading 212 Pies the user already had before adopting Loom) is `Manual` by
> default, inferred automatically through reconciliation against the live Trading 212 API — the
> user never has to declare it.

The moment the account holds one instrument outside the 4-entry map, `get_positions()` throws
and takes down the Portfolio endpoint (`loom/api/routers/portfolio.py:30`) and reconciliation
(`loom/reconciliation.py:33`) with it. An unknown ticker should degrade to an untracked
`Manual` holding, not abort the whole read.

### A5. BLOCKING — There is no FX handling anywhere in the codebase

A grep for `currency|fx|gbp|usd|exchange_rate` across `loom/` returns only comments in
`t212_tickers.py`. Nothing converts anything.

The universe mixes currencies: `VUSA.L` and `VWRL.L` are GBP on the LSE; `TSLA` and `NVDA` are
USD. `broker.get_cash()` returns `cash.availableToTrade` in the **account's** currency. Market
data returns prices in the **instrument's** currency. Then `size_and_check` computes:

```python
quantity = position_value / signal.reference_price
```

For a USD instrument in a GBP account, that divides a GBP amount by a USD price. At ~1.27
USD/GBP the order is ~27% larger than intended. The same mixing corrupts `account_value`,
exposure checks, P&L, and the daily-loss limit that arms the kill switch.

This is latent today and becomes unavoidable the moment the universe grows beyond a single
currency.

### A6. GAP — No instrument metadata

Nothing records an instrument's currency, exchange, asset class (ETF vs single equity), lot
size, minimum order value, or tradability in the connected account. Several gaps below are
downstream of this one — A5 needs currency, D5 needs ETF-vs-equity, and any liquidity filter
needs volume.

### A7. GAP — The universe is degenerate for its stated purpose

VUSA.L (S&P 500) and VWRL.L (FTSE All-World, ~60%+ US, heavily S&P-overlapping) are near-duplicates.
TSLA and NVDA are both high-beta US tech. So four instruments are really about two independent
bets.

That undermines a feature already built: cross-book correlation (`loom/correlation.py`, #38)
exists to answer "are these strategies actually diversifying." On this universe they cannot be,
regardless of strategy logic — five strategies trading two correlated things will always look
correlated. The measurement is fine; the universe makes the answer meaningless.

### A8. GAP — No per-strategy universe

One shared list serves all five strategies, but they want different instruments: Dip-Buyer needs
dividend-paying equities with real fundamentals, Compounder needs low-volatility instruments,
Breakout needs liquid instruments that actually move. A per-strategy universe (or a
tag/screen-based selection over a larger master list) is the natural model.

### A9. GAP — No liquidity, corporate-action, or delisting handling

No volume/spread filter, no check that a price series is split- and dividend-adjusted, no
handling for a halted or delisted instrument. Tolerable at 4 hand-picked instruments; not at 30.

---

## B. Data window

### B1. BLOCKING — `lookback_days` is in calendar days, but strategies need trading bars

`run_trading_pass(..., lookback_days: int = 200)` computes
`start = as_of_date - timedelta(days=200)`. **200 calendar days is ~145 trading bars.**

| Strategy / trigger | Bars needed | Bars available | Result |
|---|---|---|---|
| `ValueQualityDipBuyer` (all logic) | 200 | 145 | **never runs** |
| `TrendFollower` golden cross | 201 | 145 | never fires |
| `TrendFollower` death cross | 201 | 145 | never fires |
| `TrendFollower` 20d breakout | 21 | 145 | works |
| `LowVolCompounder` | 51 | 145 | works |
| `VolatilityHarvester` | 20 | 145 | works |
| `VolatilityBreakout` | 22 | 145 | works |

Two consequences:

- **Dip-Buyer emits nothing, ever.** Its entire loop body — entries *and* the exit check for
  held positions — sits behind `if len(closes) < window: continue`.
- **Trend Follower can buy but can never sell.** Its entry works (breakout needs 21 bars); its
  only coded exit is the death cross, which needs 201. Verified: with all four instruments held
  at +11%, Trend Follower returns zero signals.

This is the direct cause of the observed "I got signals, I bought, and then nothing — not even
sells" behaviour in demo.

### B2. GAP — Strategies fail silently when history is short

Every strategy skips with a bare `continue` when it lacks bars. No log line, no warning, no
surfaced reason. A pass that produces nothing is indistinguishable from a pass where the market
simply offered nothing. B1 went unnoticed for exactly this reason.

Strategies should declare their minimum bar requirement (e.g. `min_bars` derived from params) so
the pass can fetch enough for the hungriest strategy and report when it can't.

### B3. WRONG — Backtest and live use different history windows

The backtest engine hands strategies the **full** history, truncated only by the simulated
clock. Live hands them a 200-calendar-day window. The same strategy with the same parameters
therefore behaves differently in the two paths — Trend Follower's crossovers exist in backtest
and cannot exist live.

Backtests are currently not a faithful simulation of the live system. That matters more than any
individual parameter, because it is the mechanism we intend to use to decide whether a strategy
is worth promoting.

---

## C. Exits

### C1. BLOCKING — `ExitPlan` is never enforced in live or demo

`profit_target_pct` / `stop_loss_pct` / `time_exit_days` are enforced in exactly one place:
`loom/backtest/engine.py:check_exit`. A grep for `stop_loss|profit_target` outside the backtest,
the strategies, and the model definition returns nothing — there is no enforcement in
`trading_pass.py`, `risk.py`, or `execution/`.

Live, the only exits that exist are the ones a strategy re-derives itself on the next pass.

### C2. BLOCKING — Two strategies have no live exit path at all

Compounder, Harvester and Dip-Buyer re-check `change_pct` against `average_price` each pass, so
they self-enforce their plans. **Trend Follower and Volatility Breakout do not** — their only
coded exits are the death cross and band normalisation respectively.

Combined with C1 and B1, a Trend Follower position opened in demo today has **no exit path
whatsoever**: its stop and time exit are unenforced, and its death cross can never fire.

### C3. WRONG — Backtest results overstate the strategies that need exits most

Measured over 2019-2024, 46 of Trend Follower's 51 exits came from the stop loss (24) or time
exit (22) — mechanisms live trading does not have. Only 4 came from the death cross. The
backtest is describing a system that does not exist.

### C4. GAP — No trailing stop, and no way to build one

`PositionSnapshot` carries `instrument`, `quantity`, `average_price`, `book_id`, `add_count` —
no entry date, no peak price since entry. A trailing stop is therefore not expressible. This is
documented as a deliberate simplification in `trend_follower.py`, but for a trend-following
strategy the trailing stop *is* the strategy: with a fixed stop from entry, winners give back
everything on the way down.

### C5. GAP — Exit logic is duplicated three times

Compounder, Harvester and Dip-Buyer each independently reimplement "compare `change_pct` to
target and stop." Three copies that can drift, and none of them agrees with `check_exit`, which
is the version the backtest uses.

### C6. GAP — Exit signals can expire

`expire_stale_signals` expires any `pending_approval` signal after `DEFAULT_SIGNAL_EXPIRY_HOURS`,
with no distinction between entry and exit. A stop-loss exit left un-actioned expires like
anything else. It will be re-proposed on the next pass, but if nothing schedules a pass (F1)
that is not a safety net.

---

## D. Per-strategy logic

### D1. Low-Vol Compounder

- **WRONG — `style` contradicts ADR-0009.** The ADR assigns Compounder to `investment`. Both
  `LowVolCompounder.style` and the seeded `StrategyModel.style` (`loom/seed.py:17`) say
  `trading`. `loom/insight/research.py:23` gates the research tier on the DB column, so
  Compounder is silently denied the research tier the ADR says it should get.
- **GAP — the stop is not volatility-scaled.** `stop_loss_pct=0.02` against a
  `volatility_threshold=0.015` daily stdev is ~1.3 daily sigma. This is the *low-volatility*
  strategy and its most common outcome is being stopped out by noise: 73 stop-loss exits vs 53
  profit-target exits, average hold 16 days against a 30-day time exit.
- **GAP — confidence saturates.** `0.5 + headroom` reaches 1.0 whenever realised volatility is
  below half the threshold, which is common. Under `auto-above-threshold` this would auto-approve
  nearly everything.

### D2. Volatility Harvester

- **GAP — no trend filter.** A z-score entry with no regime check buys every falling knife by
  construction. Nothing distinguishes "oversold and will revert" from "repricing downward."
- **GAP — the payoff shape is inverted.** The z-based exit at `-0.2` clips winners before the
  6% target while the 5% stop takes full losses. Result: 59% win rate, essentially zero return
  over 6 years, 238 trades. High hit rate, negative expectancy — the classic shape.
- **GAP — no mean-reversion test.** The strategy assumes its instruments mean-revert. Nothing
  checks that, and trending instruments (NVDA, TSLA) are in the universe.

### D3. Trend Follower

- **WRONG — the two entry triggers differ by ~56x in frequency.** Counted directly over 6 years
  across 4 instruments: **731 twenty-day-high breakouts vs 13 golden crosses.** OR-ing them means
  the strategy is "buy any 20-day high" with a 1.7% golden-cross garnish.
- **WRONG — entry and exit are mismatched.** 731 potential entries are served by an exit
  (death cross) that occurred 13 times. Even ignoring B1, these do not pair.
- **GAP — no trend filter on the breakout.** A 20-day high in a downtrend is not a trend-following
  entry. The standard guard (only take breakouts above the long moving average) is absent.
- See also C2/C4 — no working live exit, no trailing stop.

### D4. Volatility Breakout

- **WRONG — the entry and exit conditions cancel each other.** Entry requires a close outside
  the bands after a squeeze; a breakout *is* a volatility expansion, and the exit fires when band
  width reaches 1.6x the squeeze low. You exit almost immediately by construction: measured
  average hold **6.6 days** against a 45-day time exit.
- **GAP — the squeeze filter is so strict it barely fires.** `was_squeezed` requires band width
  ≤ 50% of the 60-day mean *and* within 5% of the lookback low: 20 trades in 6 years across 4
  instruments.
- **GAP — confidence saturates.** `0.6 + squeeze_low/current_width` clamps to 1.0 in almost all
  cases.

### D5. Value/Quality Dip-Buyer — **cannot fire on this universe, for three independent reasons**

Even after fixing B1, this strategy produces nothing:

1. **B1** — needs 200 bars, gets 145.
2. **ETF fundamentals are absent.** VUSA.L and VWRL.L are ETFs. yfinance's `info` has no
   `trailingPE` or `debtToEquity` for them, and `_passes_quality_gate` correctly treats missing
   fundamentals as a skip. Both ETFs fail.
3. **The dividend floor excludes the rest.** `dividend_yield_floor=0.015` against TSLA (no
   dividend) and NVDA (~0.03%). Both fail — and they fail the `pe_ceiling=25` gate too.

So the pass rate over the current universe is zero, on every instrument, for reasons that have
nothing to do with whether a dip occurred.

Two further issues:

- **WRONG (needs live verification) — dividend yield units disagree between the fixture and the
  real provider.** `_FIXTURE_FUNDAMENTALS` uses fractions (`0.018` = 1.8%). yfinance's
  `info["dividendYield"]` has historically returned a *percentage* number (`1.32` for 1.32%). If
  so, the real provider passes the 0.015 floor trivially for everything and the reasoning string
  renders "132.0%". The tests only exercise the fixture, so the boundary hides the discrepancy.
  Worth confirming against the installed yfinance version before tuning anything here.
- **GAP — no historical P/E**, so "meaningfully below its own N-year average" is approximated by
  a fixed P/E ceiling. Documented in the module docstring, but the consequence is worth stating:
  a structurally cheap stock passes forever. That is the definition of a value trap, and this
  strategy has no defence against it.

---

## E. Risk and sizing

### E1. WRONG — Position and exposure limits are per-book, not account-wide

`size_and_check` receives the `AccountState` from `account_state_for_book(...)`, which contains
only that book's positions. So `max_position_size_pct=0.15` and `max_total_exposure_pct=0.9` are
enforced **per strategy**, not across the account.

CONTEXT.md says the opposite:

> Kill switch and account-level exposure/risk limits are computed across the whole `Environment`
> (every `Book` plus `Manual`)

Five strategies can each independently put 15% of account value into the same instrument — up to
75% of the account in one name, with every individual check passing. Shared cash provides some
incidental restraint, but the concentration limit as specified does not exist.

### E2. WRONG — `account_value` prices every position at the current signal's reference price

`loom/trading_pass.py:355`:

```python
account_value = account.cash + sum(p.quantity * signal.reference_price for p in account.positions)
```

Every held position is valued at *this signal's* instrument price. A book holding VUSA.L (~£75)
evaluated during an NVDA signal (~$450) values that VUSA.L position at 450. `account_value`
feeds both risk limits, so both are computed off a fabricated number whenever a book holds more
than one instrument. The backtest engine computes `equity_now` correctly per-instrument — another
live/backtest divergence.

### E3. GAP — Cash is double-counted across strategies within a pass

`cash = broker.get_cash()` is fetched once and handed to every book. Five strategies size against
the same starting balance; if several auto-approve in one pass they collectively over-commit.
Already noted in `BACKLOG.md`.

### E4. GAP — Sizing ignores volatility and confidence

A flat `position_cash_fraction` means a TSLA position and a VUSA.L position are the same size in
pounds despite ~4x the volatility. Confidence does not affect size at all. Already in `BACKLOG.md`.

### E5. GAP — Correlation is measured but never enforced

`loom/correlation.py` reports a cross-book correlation matrix. Nothing consumes it as a risk
limit — there is no "don't hold five correlated positions" check.

---

## F. Process and observability

### F1. GAP — Nothing schedules the trading pass

ADR-0002 describes a "scheduled single-pass runtime." The only workflow in `.github/workflows`
is `deploy-backend.yml`; there is no cron, no scheduler, no APScheduler. The pass runs when
someone clicks "run now" or invokes the CLI, and never otherwise.

### F2. GAP — A pass that does nothing reports nothing

Silent `continue` on short history (B2), a bare `except Exception: continue` on fundamentals
lookup in Dip-Buyer, and `PrimaryWithBackfillSource` swallowing every primary-source error. There
is no record of how many candidates each strategy evaluated, how many were rejected, and why. A
"why did I get no signals" question currently has no answer short of reading the source.

### F3. GAP — Editing `DEFAULT_PARAMS` does not change a running system

`_seed_one` returns early if the strategy row exists, so changing a strategy's `DEFAULT_PARAMS`
in code has no effect on an existing database. Parameters live in promoted
`StrategyConfigVersion` rows. This is the intended design, but it is a trap for the tuning work
ahead: every parameter change needs a new promoted version to take effect in demo.

### F4. GAP — Two sources of truth for `style`

`Strategy.style` (class attribute) and `StrategyModel.style` (DB column, set at seed time) can
disagree, and nothing reconciles them. D1's bug is currently consistent across both only by
accident.

### F5. GAP — No signal volume limiting

No per-pass or per-day cap, no cooldown, no re-entry guard beyond "skip an instrument already
held." Already in `BACKLOG.md`; it becomes urgent as soon as the universe grows.

---

## Suggested order of work

Roughly dependency-ordered rather than by severity:

1. **B1** (lookback in bars, not calendar days) and **C1/C2** (live exit enforcement) — these
   are why the demo is silent and why open positions have no way out. Nothing else can be
   evaluated until a pass behaves.
2. **F2** (pass observability) — cheap, and it is what stops the next B1 from taking weeks to
   notice.
3. **A1/A2/A6** (universe as data, with metadata and a real `universe()` on the source) and
   **A4/A5** (unmapped tickers, FX) — the prerequisites for any universe worth the name.
4. **B3/E1/E2** — make backtest and live agree, so per-strategy tuning means something.
5. Per-strategy logic, one at a time (**D1**-**D5**), each ending in an ADR.

The per-strategy work is last on purpose: tuning parameters against a backtest that does not
match live, over a universe of four instruments where one strategy cannot fire at all, would be
measuring noise.
