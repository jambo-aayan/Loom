# Manual Trading — Gap and Design Note

The ability to place a trade of your own in Loom — search an instrument, buy it; top up or sell
an open position — independent of any `Strategy`.

This is the fifth part of the gap analysis, but unlike the other four it is as much a design note
as an audit: the capability is already in the domain model, was never built, and the way it gets
built forces several decisions that are currently open.

---

## 1. It is already specified, and only half-built

`CONTEXT.md` (the `Book` entry):

> there's also a `Manual` `Book` per `Environment` for anything the user trades themselves —
> directly in Trading 212's own app, **or via a manual-trade action in Loom**

ADR-0010 says it twice:

> anything traded directly in T212's own app **or via a manual-trade action in Loom** — is
> `Manual` by default
>
> the ability to keep trading manually, in T212's own app **or via Loom**, alongside the bot

Issue #1, story 36, says "anything I trade manually, in Trading 212's app **or in Loom**."

What exists is only the **read** side. Every `manual` reference in the codebase is
`manual_positions` (`loom/reconciliation.py`) — inferring which broker holdings aren't attributed
to a strategy's `Book`. There is no write side: no endpoint, no CLI command, no UI. The `Manual`
`Book` can observe trades you made in T212's app; it cannot originate one.

This is a cleaner example of the "documented but never built" category than anything in the spec
audit, because it was never even ticketed — it isn't among issue #1's 41 sub-issues at all. It
fell through the gap between the domain model and the ticket breakdown.

---

## 2. What structurally blocks it

### 2.1 The schema cannot represent an order without a strategy

Two non-nullable foreign keys stand in the way:

```python
class Signal(Base):
    strategy_id:        Mapped[str] = mapped_column(ForeignKey("strategies.id"))            # not nullable
    config_version_id:  Mapped[str] = mapped_column(ForeignKey("strategy_config_versions.id"))  # not nullable

class Order(Base):
    signal_id:          Mapped[str] = mapped_column(ForeignKey("signals.id"))               # not nullable
```

So **every `Order` must have a `Signal`, and every `Signal` must have both a `Strategy` and a
`StrategyConfigVersion`**. A manual trade has none of the three. As the schema stands, a manual
trade cannot be recorded at all.

Notably, the codebase has already solved this exact problem once — for `Book`:

```python
class Book(Base):
    """strategy_id is null for the `Manual` book of a given environment."""
    strategy_id: Mapped[str | None] = mapped_column(ForeignKey("strategies.id"), nullable=True)
```

`Book.strategy_id` is the *only* nullable `strategy_id` in the schema, and null already means
"manual". `Signal` is inconsistent with a convention the project has already established.

### 2.2 Only four instruments can be ordered at all

`to_t212` raises `UnmappedInstrumentError` for anything outside the four-entry
`LOOM_TO_T212` map. Today you could not manually buy AAPL through Loom even if every other piece
existed — the order would fail locally before reaching T212.

The module docstring anticipates exactly this moment:

> Deliberately a static map, not a dynamic lookup against T212's
> `/equity/metadata/instruments` ... a dynamic metadata-backed lookup is worth building once the
> universe is no longer a small fixed list, not before.

The T212 client currently implements three methods — `submit_order`, `get_positions`, `get_cash`.
There is no instruments-metadata call, so there is nothing to search.

This is the "bring through all the instruments" piece, and it's the same work that unblocks four
other findings: the hardcoded universe (gap analysis A1), missing instrument metadata (A6), the
unmapped-ticker crash on the live ISA (A4), and per-strategy universes (A8). Manual trading is
the forcing function that makes it worth doing properly rather than extending the dict by hand.

### 2.3 The one good piece of news

`broker.submit_order` has exactly one caller in the entire codebase: `execute_signal` in
`trading_pass.py:370`. Every safety control — kill switch check, live trading gate, risk/sizing
re-check, idempotency key, order recording, failure handling — lives in that one function.

That means a manual trade should route **through** `execute_signal`, not around it. There is a
single correct place to add this, and taking any other path would silently bypass the kill
switch. Worth stating explicitly because "it's my own trade, it doesn't need the safety layer" is
a tempting shortcut, and CONTEXT.md is unambiguous that the kill switch is checked "immediately
before every order submission."

---

## 3. Recommended shape

### 3.1 Model a manual trade as a `Signal` with a null strategy

Make `Signal.strategy_id` and `Signal.config_version_id` nullable, with null meaning
user-originated — matching `Book`'s existing convention.

The alternative — making `Order.signal_id` nullable and adding a separate manual-order table —
is worse: `booked_trade_for_signal` (ADR-0015), History, per-`Book` P&L, `SignalOut`, and every
evaluation path all traverse `Order → Signal`. A null `signal_id` breaks all of them. A
null-strategy `Signal` breaks none, because the only thing downstream code needs from
`strategy_id` is attribution, which a `Book` already carries independently.

A manual trade then flows through the machinery unchanged: it gets a `Signal` row (status
`approved`, `requires_manual_approval` moot since the user *is* the approver), an `Order` through
`execute_signal`, a `Book` assignment, and it appears in History next to strategy signals with
its own realised P&L.

This does require a decision about the `Signal` glossary entry in `CONTEXT.md`, which currently
reads "The output of the strategy/idea-generation layer." That definition would need widening, or
a sibling term introduced. That is a `/domain-modeling` conversation, not an implementation
detail — and worth having before the code, since the glossary is the project's shared vocabulary.

### 3.2 Sync T212's instrument metadata into a real table

Add `get_instruments()` to the T212 client (`GET /equity/metadata/instruments`), and a scheduled
job to sync it into an `instruments` table: Loom ticker, T212 ticker, name, currency, exchange,
asset type, minimum trade quantity.

That table then replaces the static `LOOM_TO_T212` dict, powers instrument search for manual
trading, gives the universe a real home (A1), supplies the currency field FX handling needs (A5),
and lets `from_t212` resolve the live ISA's holdings instead of raising (A4).

A multi-thousand-row response synced on a schedule (it changes rarely) and served from the DB is
a very different cost profile from looking it up per call — which is what the original docstring
was rejecting, not the idea of dynamic lookup itself.

---

## 4. Open questions — these need deciding, not assuming

### 4.1 Do risk limits apply to a manual trade?

The kill switch clearly must — it is a global halt, and CONTEXT.md is explicit.

The position-size and exposure caps are genuinely arguable. They exist so "no single trade or bad
day can do outsized damage" (story 24), and that reasoning doesn't stop applying because a human
typed the order. But they were also written to constrain *strategies*, and a deliberate human
decision is a different thing from an algorithm firing at 08:00.

Three options: hard-enforce, warn-and-allow-override, or exempt entirely. **Recommendation:**
warn-and-allow-override, with the override recorded on the `Signal` — it keeps the limits
meaningful, keeps you in control of your own account, and leaves an audit trail of when you chose
to exceed them, which is exactly the kind of decision this project exists to help you evaluate.

### 4.2 Does a manual trade carry an exit plan?

If it does, a manual position can be managed by the same exit enforcement the strategies need
(gap analysis C1/C2) — you'd set a target and stop at entry and Loom would act on them.

If it doesn't, a manual position is a pure hold until you sell it manually.

**Recommendation:** optional. Default to none, offer target/stop fields at entry. This is a small
decision now but it should be made *alongside* the exit-enforcement design rather than after,
since both answer "where does exit logic live."

### 4.3 Buy by value or by quantity?

T212's market-order API takes a **quantity** (rounded to 4dp). Entering "£100 of AAPL" means
computing `quantity = value / price` — and Loom has no live quote for an instrument it doesn't
already hold. T212 exposes `currentPrice` only on existing positions; Twelve Data's close is up
to ~1hr stale (ADR-0008). This is the same staleness problem already logged in `BACKLOG.md` for
strategy sizing, and it bites harder here because you'd see a figure in the UI and expect it to
be what you spend.

**Recommendation:** quantity entry first (exact, no estimation), with value entry as a follow-up
once there's a live-quote answer. Worth confirming you're happy with that, since value entry is
how T212's own app works and it may be what you expect.

### 4.4 What happens when you manually sell a strategy's position?

This is the subtlest one, and it matters most for what the project is actually for.

If you manually sell a Low-Vol Compounder holding, does that sale count in Compounder's `Book`
and therefore in its track record?

- **Stays in the strategy's Book**: the strategy's P&L reflects a decision it didn't make. Its
  win rate now includes your intervention.
- **Moves to Manual first, then sells**: Compounder's record stays pure, but its position
  silently leaves its book, which distorts the other direction.

**Recommendation:** keep it in the strategy's `Book` but flag the `Signal` as user-initiated, so
evaluation can report both "Compounder's own decisions" and "Compounder including your
overrides." Given the whole counterfactual layer exists to tell you whether your judgment adds or
subtracts value (ADR-0011), being able to separate those two numbers is the point — and merging
them would quietly destroy the measurement.

CONTEXT.md already gestures at this boundary: "Moving a position into a different `Strategy`'s
management is a deliberate user action, never something a `Strategy` decides on its own." Manual
intervention in a strategy's position is the mirror image of that sentence and deserves the same
explicitness.

---

## 5. Sizing the work

Roughly, in dependency order:

1. **Instrument metadata sync** — client method, table, migration, scheduled job, replace the
   static map. The largest piece, and the one with the widest payoff across other findings.
2. **Schema change** — nullable `strategy_id`/`config_version_id` on `Signal`, plus a
   user-initiated flag. One migration.
3. **Manual trade endpoint** — validate, build a `Signal`, route through `execute_signal`.
   Small, because the execution path already exists and is correct.
4. **Instrument search endpoint** — query the new table.
5. **UI** — search-and-buy, plus buy/sell actions on the Overview position cards. Fits naturally
   with the Overview rework already identified (UI audit §1.1-1.3), since both change the same
   position card.

Steps 2-4 are small. Step 1 is the real work, and it's work four other findings already wanted.

Note this does **not** depend on the backtest engine, the strategy logic, or calibration — none
of which manual trading touches. It is close to an independent track.
