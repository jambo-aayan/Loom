# 22. Manual trading: a `Signal` with no `Strategy`

## Status

Accepted

## Context

Placing a trade of your own in Loom — search an instrument and buy it, top up or sell an open
position, independently of any `Strategy` — has been in the domain model since the beginning.
`CONTEXT.md`'s `Book` entry, ADR 0010 twice, and issue #1's story 36 all say a trade may be made
"in Trading 212's own app **or via Loom**."

Only the read half was ever built. `reconciliation.py` infers which broker holdings are not
attributed to a `Strategy`'s `Book` and files them as `Manual`, so the `Manual` `Book` can
observe a trade you made in T212's app but cannot originate one. It was never even ticketed — it
is absent from issue #1's 41 sub-issues, having fallen through the gap between the domain model
and the ticket breakdown.

Three things block the write half:

1. **The schema requires every order to have a strategy.** `Order.signal_id`,
   `Signal.strategy_id` and `Signal.config_version_id` are all non-nullable, so a trade with no
   strategy behind it cannot be recorded at all.
2. **Loom knows four instruments.** `LOOM_TO_T212` is a hand-written four-entry map and
   `to_t212` raises for anything else, so a manual buy of AAPL would fail locally before reaching
   T212. The T212 client implements `submit_order`, `get_positions` and `get_cash` and nothing
   else — there is no instrument metadata call, so there is nothing to search.
3. There is no endpoint, CLI command or UI.

The one piece of good news is that `broker.submit_order` has exactly one caller in the codebase:
`execute_signal`. Every safety control — kill switch, live trading gate, risk check, idempotency
key, order recording — lives in that one function.

## Decision

### A manual trade is a `Signal` with a null `Strategy`

`Signal.strategy_id` and `Signal.config_version_id` become nullable, with null meaning
user-originated. This matches a convention the project already has: `Book.strategy_id` is
nullable and null already means `Manual`.

The alternative — making `Order.signal_id` nullable and adding a separate manual-order table —
is worse. `booked_trade_for_signal` (ADR 0015), `History`, per-`Book` P&L, `SignalOut` and every
evaluation path traverse `Order → Signal`; a null `signal_id` breaks all of them. A
null-`Strategy` `Signal` breaks none, because the only thing downstream code wants from
`strategy_id` is attribution, which the `Book` already carries.

A manual trade then flows through the existing machinery unchanged, and — the actual point —
appears in `History` next to strategy signals, measured the same way. Recording it differently
would make the comparison the project exists to draw impossible to draw.

### It routes through `execute_signal`, not around it

"It's my own trade, it doesn't need the safety layer" is the tempting shortcut and it is wrong:
`CONTEXT.md` is unambiguous that the kill switch is checked immediately before every order
submission. Since every control lives in one function, there is exactly one correct place to add
this, and any other path silently bypasses the kill switch.

### Risk limits warn; the kill switch does not

Position-size and exposure caps apply to a manual trade but may be overridden, and the override
is recorded on the `Signal`. They exist so no single trade can do outsized damage, and that
reasoning does not stop applying because a human typed it — but they were written to constrain
algorithms, and a deliberate human decision is a different thing.

The kill switch is not overridable. It is a global halt, not a limit.

Recording the override matters beyond audit: "when did I decide to exceed my own limits, and how
did those trades do" is exactly the kind of question `History` exists to answer.

### A manual trade may carry an `Exit plan`, optionally

Offered at entry, defaulted to none. With one, the position is managed by the same enforcement
layer as a `Strategy`'s; without one, it is a plain hold until sold.

This costs nothing to support — `CONTEXT.md` already states that any `Position` carrying a plan
is honoured in any `Book`, and enforcement was deliberately built to read the plan rather than
ask the strategy. It also enables something worth having: running a strategy's logic by hand,
against the same strategy running automatically, and comparing.

### Buy by quantity first, by value later

T212's market-order API takes a quantity. Entering "£100 of AAPL" requires a live quote, and Loom
has none for an instrument it does not already hold — T212 exposes `currentPrice` only on
existing positions, and market data is up to an hour stale (ADR 0008). Showing "£100" and
spending £103 is worse than asking for a quantity.

Value entry is how T212's own app works and is the better end state; it waits on a live-quote
answer rather than being faked with a stale one.

### Manually selling a `Strategy`'s position keeps it in that `Strategy`'s `Book`

The `Signal` is flagged user-initiated, so evaluation can report both "the `Strategy`'s own
decisions" and "the `Strategy` including your overrides."

Leaving it in the `Book` unflagged would fold your intervention into the strategy's track record.
Moving it to `Manual` first would make positions silently leave a `Book`, distorting the record
the other way. Both destroy the same measurement: ADR 0011's whole purpose is telling you whether
your judgment adds or subtracts value, which requires the two numbers to be separable.

### Instrument metadata becomes a real table

`get_instruments()` is added to the T212 client and a scheduled job syncs
`GET /equity/metadata/instruments` into an `instruments` table — Loom ticker, T212 ticker, name,
currency, exchange, asset type, minimum trade quantity.

That table replaces `LOOM_TO_T212`, powers instrument search, gives the universe a real home,
supplies the currency and asset-type fields ADR 0019's cost model needs to know whether FX and
stamp duty apply, and lets `from_t212` resolve the live ISA's holdings instead of raising.

The original docstring rejected "a dynamic lookup against `/equity/metadata/instruments` on every
call". This is not that: a multi-thousand-row response synced on a schedule and served from the
database is a different cost profile, and the same docstring anticipated the moment — "worth
building once the universe is no longer a small fixed list."

## Consequences

- Two non-nullable columns become nullable, which is a migration and a review of every code path
  that assumes a `Signal` has a `Strategy`. `SignalOut`, `History` and the evaluation paths all
  need a null case.
- The instrument sync is the largest piece here and is shared: ADR 0021's Compounder universe
  cannot be defined without it either.
- Value-based entry is deferred, and it is what a T212 user expects. If quantity-only proves
  annoying in practice, the live-quote work moves up rather than the estimate being faked.
- A user-originated `Signal` has no `Strategy config version`, so it cannot be attributed to a
  configuration and never participates in promote/demote comparisons. That is correct, and worth
  stating so nobody later tries to give manual trades a synthetic version.
