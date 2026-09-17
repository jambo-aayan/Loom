# Context

Domain glossary for the Trading 212 trading bot. This file defines project vocabulary only — no implementation details, no strategy parameters, no architecture decisions (those live in `docs/adr/`).

## Terms

**Signal**
A proposed trade, before risk/sizing rules are applied — the one unit that enters the risk → approval → execution pipeline, whatever proposed it. Most `Signal`s come from the strategy/idea-generation layer; a `Signal` realising an `Exit plan` is proposed by Loom's exit enforcement instead, and is attributed to the `Strategy` whose `Book` holds the position, since it realises that `Strategy`'s own plan. A `Signal` may also be proposed by the user directly — a trade of their own choosing rather than any `Strategy`'s — in which case it belongs to no `Strategy` at all. A user-originated `Signal` is still a `Signal`: it is sized, checked, executed, recorded and evaluated by the same machinery, because the point of `History` is to compare the user's judgment against the `Strategy`s' on equal terms, and a trade recorded differently cannot be compared. Canonical term — do not use "suggestion" or "trade idea" interchangeably with this; those were used loosely in early discussion but `signal` is the one name for this concept going forward.

A `Signal` becomes a sized `Order` after the risk/sizing layer approves and scales it. An `Order` becomes a `Position` once filled.

A `Signal`'s lifecycle: `proposed` → (`auto-approved` or `pending-approval`, per its `Strategy`'s `Approval mode`) → (`approved` or `rejected`, or `expired` if left un-actioned) → `executed`.

Every `Signal` is retained permanently, regardless of outcome — approved, rejected, expired, or auto-executed. A rejected or expired `Signal` is not a dead record: it's evaluated after the fact via its `Counterfactual outcome` (see below), which is the entire point of keeping it. At the moment of `approved`/`rejected`, the user may optionally attach a free-text `Note` explaining their reasoning — this is what makes `History` a genuine trade journal, not just a log.

**Exit plan**
The conditions under which a `Position` will be closed, declared on the `Signal` that opened it and fixed at that moment: a profit target, a stop loss, a trailing stop, and/or a time limit. Every `Signal` carries one — a `Strategy` may not propose an entry without declaring how it intends to leave.

Its levels are expressed as multiples of the instrument's own volatility, not as fixed percentages. A level is a claim about how much movement is *meaningful* for that instrument, and what counts as meaningful is a property of the instrument rather than a constant — the same 2% is a noisy afternoon in one name and a month in another. Levels are **gross**: they describe price movement, not a return net of `Round-trip cost`. A time limit is counted in trading days, like every other window a `Strategy` uses.

The volatility the levels are multiples of is measured once, at entry, and fixed there with the rest of the plan — never re-measured while the `Position` runs. A re-measured level widens exactly when volatility spikes, which is when a stop is most needed, and leaves a plan that cannot be reconstructed afterwards from what was known at the time.

An `Exit plan` is enforced by Loom, never left with the broker (Trading 212 offers market orders only). Enforcement belongs to Loom rather than to the `Strategy` that wrote the plan: any `Position` carrying a plan is honoured, in any `Book`. A `Position` built from several entries — a `Volatility Harvester` add, say — is governed by the plan of the `Signal` that opened it, which later adds inherit rather than replace; its levels are measured against the position's blended average cost, since the position is one economic unit.

Distinct from a **discretionary exit**: an `Exit plan` realises a level calculated at entry and is arithmetic, while a discretionary exit (a trend reversal, a volatility regime change) is a fresh judgment a `Strategy` makes about conditions that have changed since. The distinction decides whether a human is asked — see `Approval mode`.

**Round-trip cost**
What one complete trade in an instrument costs before any price movement: currency conversion charged on both the buy and the sell for anything not priced in the account's currency, stamp duty charged on the purchase of some instruments and not others, and the spread paid on entering and leaving. A property of the instrument, not of the `Strategy` trading it.

It is the floor a `Strategy` has to clear to be worth running at all: a design whose typical win is a small multiple of its own `Round-trip cost` is converting activity into fees. Checked when a `Strategy config version` is promoted, because that is when the design is chosen — noticing it in realized P&L means noticing after the money has gone.

Every figure Loom reports as profit or loss is net of what was actually charged, including a `Counterfactual outcome`'s hypothetical result. A rejected `Signal` measured gross against real trades measured net would make every rejection look better than it was, which would quietly corrupt the one thing `History` exists to measure.

**Counterfactual outcome**
For a `Signal` that was rejected or expired (never became a real `Order`), Loom keeps simulating it forward as a shadow position — same simulated-fill mechanics the backtest engine already uses, starting from the `Signal`'s proposed entry and applying that `Signal`'s own `Exit plan` against real subsequent market data (the plan only — a `Strategy`'s discretionary exits are not re-evaluated, so a counterfactual for a strategy that exits discretionarily is an approximation) — until that shadow position would have exited (target/stop hit) or a max horizon is reached. The result (hypothetical P&L, still-open, or hit-target/hit-stop) is attached back to the `Signal` record, so `History` can show "you rejected this — it would have gained +6.2%" next to "you approved this — it's up 3.1%," across every strategy and every decision, not just the ones that were acted on. This is a deliberate learning tool: the goal is to see whether your own approve/reject judgment is adding value or subtracting it.

**Confidence**
A 0–1 score a `Strategy` attaches to each `Signal` it proposes, expressing how strongly it believes in that trade (continuous, not a binary confident/not-confident flag — e.g. 0.2, 0.4, 0.6...). Drives `Approval mode` when a strategy is set to `auto-above-threshold`.

**Expected value**
What one `Signal` is worth in expectation, per unit of capital: its `Confidence` weighed against the gain and loss its own `Exit plan` describes, less the instrument's `Round-trip cost`. Derived by Loom from things the `Signal` already carries — never supplied by a `Strategy`, which would let one strategy claim its way to the front of the queue.

Distinct from `Confidence`, and the distinction decides who gets funded. `Confidence` is a belief about whether a trade will work; `Expected value` is what acting on that belief is worth. A strategy that is right 70% of the time for a small gain has high `Confidence` and modest `Expected value`; one that is right 35% of the time for a large gain has the reverse. Ranking scarce capital by `Confidence` alone would fund the first and starve the second, however much better the second is.

So the two are used in different places: `Approval mode` compares `Confidence` against a threshold, because a human deciding whether to approve is asking "will this work?"; the capital budget ranks by `Expected value`, because capital is asking "what is this worth?"

**Approval mode**
A per-`Strategy` setting controlling whether its `Signal`s need a human's explicit approval before becoming an `Order`. Three values: `manual` (always needs a human click — the default for every strategy until proven), `auto-above-threshold` (auto-approves only when `Confidence` clears a configured bar, else queued for manual approval), `auto` (always auto-approves). Distinct from sizing: approval decides *whether* a trade proceeds; the risk/sizing layer still decides *how much*.

**Kill switch**
The mechanism to immediately halt the bot from submitting further orders. Checked by the execution layer immediately before every order submission. Not only manually flipped — the daily loss limit check (`loom.daily_loss`) auto-engages it the moment a day's account value drops past `RiskLimits.daily_loss_limit_pct` against that day's opening snapshot, with no human in the loop. Once engaged, by either path, every order silently short-circuits to a failed `Order` (no exception, no broker call) until a human explicitly resumes it in Settings — nothing resumes it on its own, even once the underlying condition that triggered it has resolved.

**Strategy**
A pluggable component that generates `Signal`s from market data, current positions, and account state. v1 ships five concrete strategies (see `docs/adr/0009-v1-strategy-roster.md`), each independently identifiable (every `Signal` carries the `strategy_id` of the `Strategy` that produced it) and independently evaluable (performance is tracked per strategy via its own `Book`, not just in aggregate). The `Strategy` interface is designed to support many more than five; the system was never meant to have only one.

A `Strategy` has `live-enabled` (bool, default `false`): whether it's permitted to place real-money orders at all. This is a one-way-until-you-say-otherwise permission gate, not a phase it moves through — a `Strategy` can always be run against the `demo` `Environment` regardless of its `live-enabled` value; enabling it only additionally allows `live` orders. Promotion is a manual decision the user makes after reviewing the strategy's track record; there's no auto-promotion.

A `Strategy` also has a **style**: `trading` (shorter hold, technical, exits are frequent) or `investment` (longer hold, conviction-based, benefits most from deep `Insight` research). This is descriptive metadata, not a behavioral gate — it informs which strategies get the deeper research tier and how their `Book`'s performance should be read, not a hard rule enforced by the system.

**Trade**
A round-trip: one or more entry `Order` fills paired, FIFO, against the exit `Order` fill(s) that closed them, carrying a realized P&L. Distinct from `Signal` (the proposal), `Order` (the sized instruction sent to the broker), and `Position` (the current open holding) — a `Trade` only exists once a `Position` has actually been closed out. The backtest engine has this concept as `TradeRecord`; live/demo trading has it as `reconstruct_closed_trades()`'s `ClosedTrade`, FIFO-matched from real `Order` history — the same reconstruction Performance/evaluation already use. See `docs/adr/0015-live-trade-ledger.md`.

Booked profit is surfaced two ways: permanently on `History` next to the closing `Signal` as `booked_trade` (part of the same "everything about a decided signal stays visible" rule that already applies to reasoning and exit-plan numbers), and as an immediate confirmation the moment a sell executes (e.g. "Sold VUSA.L, booked +£12.40 (+3.1%)") — both read from the same underlying reconstruction, not a separately-tracked number.

**Live trading gate**
A single global on/off switch, independent of any per-`Strategy` `live-enabled` flag, that must also be on before Loom will place a single live `Order`. Off by default. Distinct from `Kill switch` (which halts order submission in general, in either `Environment`, and is meant to be flipped in an emergency) — the live trading gate is the deliberate, one-time step of leaving Phase 1 (demo-only) and turning live trading on at all; while it's off, the `live` `Environment` isn't even selectable in the frontend, and the backend independently refuses to run a live trading pass regardless of what the frontend shows.

**Auto-trading gate**
A single global on/off switch controlling whether any `Strategy`'s `Approval mode` is allowed to auto-approve at all. Governs entries and discretionary exits only: a `Signal` realising an `Exit plan` is never gated by it, since a circuit breaker that stopped you closing losing positions would be the wrong shape. When off, every other `Signal` is forced to `pending_approval` regardless of a `Strategy`'s configured `Approval mode` or `Confidence` — a non-destructive circuit breaker, not a mutation of the stored `Approval mode`: turning the gate back on immediately restores each `Strategy`'s own configured behavior with no re-configuration needed.

**Strategy config version**
A `Strategy`'s parameters (thresholds, windows, sizing rules) are not just "whatever's in the code" — each change is a new numbered version. Every `Signal` and every backtest run records which version of its `Strategy` produced it, so a parameter tweak ("move the RSI threshold from 4 to 3") is a traceable, comparable event: you can see exactly what changed and how the strategy's real and backtested performance differed before and after, not just that performance changed at some point.

A version starts as a **draft**: an edited-but-not-yet-official parameter set (still a code/config change per `BACKLOG.md`'s no-code-tuning entry — drafting isn't a UI for editing values, it's a status on a version) that can be backtested like any committed version before the user decides whether to promote it. Promoting a draft is what assigns it its permanent number and makes it the `Strategy`'s current config; an un-promoted draft never produces live `Signal`s. This is distinct from `live-enabled`, which gates a whole `Strategy` for real-money orders, not a single config version.

**Book**
A named, software-level ledger bucket that owns a set of `Position` lots, scoped to one `Environment`, for P&L attribution. Every `Strategy` gets exactly one `Book` per `Environment` (e.g. "Low-Vol Compounder · Live"); there's also a `Manual` `Book` per `Environment` for anything the user trades themselves — directly in Trading 212's own app, or via a manual-trade action in Loom. A position is assigned to a `Book` at the moment `Loom` executes the order that opened it; anything found in the real account that isn't tagged to a `Strategy`'s `Book` (including pre-existing Trading 212 Pies the user already had before adopting Loom) is `Manual` by default, inferred automatically through reconciliation against the live Trading 212 API — the user never has to declare it.

A `Strategy` may generate an advisory `Insight` about a position in *any* `Book`, including `Manual` and other strategies' — but a `Signal` (actionable, approvable) can only ever be proposed against the `Book` owned by the `Strategy` that generated it. Moving a position into a different `Strategy`'s management is a deliberate user action, never something a `Strategy` decides on its own.

The same instrument may be held in more than one `Book` at once, deliberately: a long-term holding in one `Book` and a `Strategy` trading around it in another is a supported shape, not a conflict. Each `Book` owns its own lots and its own `Exit plan` for them, and the broker sees only the aggregate. What is not allowed is two `Book`s trading the same instrument in opposite directions in one pass — the entry waits, the exit never does, since paying to buy and sell the same thing on the same day leaves exposure unchanged and the fees gone.

Kill switch and account-level exposure/risk limits are computed across the whole `Environment` (every `Book` plus `Manual`), since ISA cash and exposure are genuinely shared. Because one instrument can sit in several `Book`s, the limit on how much of it the account holds is one account-wide number rather than a per-`Book` one — a per-`Book` capital allocation limit is a separate, additional layer on top, not a replacement for the account-level check.

**Notify threshold**
A per-`Strategy` setting, separate from `Approval mode`'s auto-above-threshold bar, controlling which `Signal`s are worth interrupting the user for via a push notification or notification-style email (see `docs/adr/0012-mobile-and-notifications.md`) — e.g. "notify me for anything ≥ 0.85 confidence." Distinct from `Approval mode`: a `Signal` can require manual approval *and* be worth an immediate push (the common case this exists for), or be low enough confidence that it's fine to just pile up in the Approvals queue unnoticed until the user next opens the app.

**Environment**
`demo` or `live` — which Trading 212 account (and therefore which base URL/API key) a given `Signal`, `Order`, or `Position` belongs to. Not a phase or a one-time deployment setting: both environments are always available side by side, and the UI has an explicit switch between them (comparable to an exchange's testnet/live toggle), so the user can test any `Strategy` against `demo` at any time independent of what's currently running on `live`.

**Insight**
LLM-generated advisory content — commentary on why a specific `Signal` fired, or on-demand research about a stock/macro topic. Deliberately distinct from `Signal`: an `Insight` is never actionable on its own and can never directly trigger an `Order`; it only informs a human or, if a future `Strategy` implementation chooses to use one as an input, that `Strategy`'s own signal generation (still subject to the same risk/sizing and approval gates as any other `Signal`).

`Insight` generation happens in two tiers (see `docs/adr/0009-v1-strategy-roster.md`, `docs/adr/0013-dual-provider-insight-research.md`): a cheap **screening** pass (news/sentiment summary, runs on every candidate, cheap/free model) and a deeper **research** pass (multi-source synthesis, a written thesis).

The **research** tier is gated by `Strategy` style, not just cost: it only ever runs for `investment`-style candidates (their longer-hold, conviction-based nature is exactly the case that needs company-level context beyond what a rules-based signal already expresses) — `trading`-style strategies never get more than the screening tier, regardless of confidence or how the tier is invoked. Within that gate, research has two invocation modes: a **free** pass that runs automatically once an `investment`-style candidate reaches `pending_approval`/`auto_approved`, and a **paid**, meaningfully stronger pass that is exclusively user-triggered — it is never scheduled, never batched, and never fires as a side effect of anything else; invoking it always asks the user to confirm first, since it costs real money per call.

## Open / not yet resolved

- Vocabulary for the strategy's target universe (e.g. "low-volatility large caps and indices") — not yet formalized as a term.
