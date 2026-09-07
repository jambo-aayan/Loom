# 15. Surfacing live/demo `Trade` realized P&L: reuse the existing FIFO reconstruction

## Status

Accepted

## Context

The backtest engine already has a round-trip concept: `TradeRecord` (`backtest/engine.py`) pairs
an entry fill with the exit fill that closed it, and carries a real computed P&L.

Live/demo trading turns out to already have a *better* equivalent than initially assumed:
`loom/trade_reconstruction.py`'s `reconstruct_closed_trades()` does real FIFO lot-matching against
a Book's filled `Order` history — the same reconstruction Performance/evaluation (#37) and
correlation/fundamentals already depend on. It was never reused everywhere, though: the Strategy
detail page's trade log (`GET /strategies/{id}/trades`) computed its own separate, cruder number
instead — every `sell` fill's return against that fill's own `Signal.reference_price`, summed
cumulatively, not the position's real FIFO cost basis, and with no notion of which entry a given
exit closed out. An earlier version of this ADR proposed a brand-new `Trade` database table with
its own average-cost accounting before this was noticed — that would have been a second,
divergent cost-basis implementation sitting next to a better one already in the codebase, exactly
the "Duplicated Code" problem to avoid. This ADR corrects course: extend and reuse
`reconstruct_closed_trades`, don't duplicate it.

The user asked for exactly what `TradeRecord`/`ClosedTrade` already models: the realized P&L of
"we bought at X, sold at 1.2X" — plus wanting that number the moment a sell executes, not just
aggregated on a chart.

## Decision

- `ClosedTrade` (the dataclass `reconstruct_closed_trades` returns) gains an `exit_order_id`
  field, so a caller can ask "which closed trade(s) did this specific sell Order produce?" — a
  single sell fill can close more than one FIFO lot, so this is one-to-many, not one-to-one.
- No new database table. Realized P&L is derived on read from existing `Order`/`Signal` history,
  the same way `book_positions()` already derives open positions — there is nothing to keep in
  sync, and it can never diverge from the numbers Performance/evaluation already show.
- `Signal.booked_trade` (a Python property, not a mapped column) aggregates the `ClosedTrade`(s)
  a sell `Signal`'s fill produced into one `BookedTrade` value — `instrument`, `quantity`,
  `exit_price`, `realized_pnl`, `realized_pnl_pct` — exposed on `SignalOut` as `booked_trade`.
  This is what makes "tell me what profit we're booking" available immediately on the same
  response the approval/execution call already returns, and permanently thereafter on `History`
  (CONTEXT.md's existing "everything about a decided signal stays visible" rule already covers
  keeping it there).
- `GET /strategies/{id}/trades`'s realized-return math is replaced with the same
  `reconstruct_closed_trades` call, grouped by `exit_order_id`, instead of its old proxy.

## Consequences

- One correct FIFO cost-basis implementation instead of a proposed second, divergent one — the
  fix this ADR should have proposed from the start.
- `Signal.booked_trade` re-walks the whole Book's order history on each access
  (`reconstruct_closed_trades` isn't incremental). Fine at v1's per-strategy order volumes; if
  this becomes a real cost, memoizing or incrementalizing `reconstruct_closed_trades` itself
  would benefit every caller, not just this one — another reason not to have built a second,
  narrower implementation.
- A strategy that only ever holds a single lot of a single instrument (true of v1's five
  strategies today) sees numbers that already matched what Performance/evaluation compute; only
  the old Strategy-detail trade log's numbers actually change (from proxy to correct).
