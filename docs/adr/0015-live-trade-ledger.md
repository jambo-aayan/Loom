# 15. A real `Trade` ledger for live/demo trading, replacing the crude per-fill proxy

## Status

Accepted

## Context

The backtest engine already has a proper round-trip concept: `TradeRecord` (`backtest/engine.py`)
pairs an entry fill with the exit fill that closed it, and carries a real computed P&L. Live and
demo trading never got the equivalent. Today, `GET /strategies/{id}/trades` computes what its own
code comments call "a crude realized-return proxy per fill": every `sell` fill's return is
computed against that fill's own `Signal.reference_price` and summed cumulatively across the
whole strategy, not against the actual position's cost basis, and with no notion of which entry a
given exit closed out. It happens to be directionally right for a strategy that only ever holds
one lot of one instrument at a time, but it isn't a real ledger, and it can't answer "what did we
just book on that sell?" for a specific `Position`.

The user asked for exactly the thing `TradeRecord` already models for backtests: the realized
P&L of "we bought at X, sold at 1.2X" — plus wanting that number the moment a sell executes, not
just aggregated on a chart.

## Decision

- Introduce a `Trade` concept for live/demo trading, structurally mirroring backtest's
  `TradeRecord`: one row per closed round-trip, referencing the entry `Order` and the exit
  `Order` that closed it, with `quantity`, `entry_price`, `exit_price`, `realized_pnl`, and
  `realized_pnl_pct`.
- Cost basis is tracked per `Book` using the same running average-cost accounting
  `trading_pass.py` already computes for open `PositionSnapshot`s (`book_positions()`), rather
  than inventing a second cost-basis method: a sell fill closes out (up to) the position's whole
  average-cost lot for that instrument, and the `Trade` record is built from that lot's average
  entry price against the sell's fill price. `book_positions()` blends all buy fills for an
  instrument into a single running average price, not discrete FIFO lots — v1's five strategies
  each hold at most one lot per instrument, so this stays accurate for the trading this ledger
  needs to cover today; a strategy that intentionally stacks distinct entry lots would need this
  revisited to preserve per-lot P&L rather than an average.
- A `Trade` is created synchronously at the moment a sell `Order` fills (`execute_signal`), not
  computed lazily from a query — this is what makes "tell me what profit we're booking" possible
  immediately, not just derivable after the fact from History.
- The `GET /strategies/{id}/trades` endpoint's realized-return math is replaced by reading real
  `Trade` rows instead of recomputing the proxy.

## Consequences

- Replaces an approximation with an actually-correct number, at the cost of a new table and a
  small amount of bookkeeping in the fill path (`execute_signal`), which already has access to
  everything a `Trade` needs (the filling `Order`, its `Signal`, and the `Book`'s open lots).
- The average-cost logic isn't new — it already exists for computing open positions — this reuses
  it rather than adding a second, possibly-diverging cost-basis implementation.
- A strategy that only ever holds a single lot of a single instrument (true of v1's five
  strategies today) will see identical numbers to before; the correctness improvement matters the
  moment any strategy holds multiple concurrent lots or instruments.
