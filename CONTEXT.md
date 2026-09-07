# Context

Domain glossary for the Trading 212 trading bot. This file defines project vocabulary only — no implementation details, no strategy parameters, no architecture decisions (those live in `docs/adr/`).

## Terms

**Signal**
The output of the strategy/idea-generation layer: a proposed trade, before risk/sizing rules are applied. Canonical term — do not use "suggestion" or "trade idea" interchangeably with this; those were used loosely in early discussion but `signal` is the one name for this concept going forward.

A `Signal` becomes a sized `Order` after the risk/sizing layer approves and scales it. An `Order` becomes a `Position` once filled.

A `Signal`'s lifecycle: `proposed` → (`auto-approved` or `pending-approval`, per its `Strategy`'s `Approval mode`) → (`approved` or `rejected`, or `expired` if left un-actioned) → `executed`.

Every `Signal` is retained permanently, regardless of outcome — approved, rejected, expired, or auto-executed. A rejected or expired `Signal` is not a dead record: it's evaluated after the fact via its `Counterfactual outcome` (see below), which is the entire point of keeping it. At the moment of `approved`/`rejected`, the user may optionally attach a free-text `Note` explaining their reasoning — this is what makes `History` a genuine trade journal, not just a log.

**Counterfactual outcome**
For a `Signal` that was rejected or expired (never became a real `Order`), Loom keeps simulating it forward as a shadow position — same simulated-fill mechanics the backtest engine already uses, starting from the `Signal`'s proposed entry and applying the originating `Strategy`'s own exit logic against real subsequent market data — until that shadow position would have exited (target/stop hit) or a max horizon is reached. The result (hypothetical P&L, still-open, or hit-target/hit-stop) is attached back to the `Signal` record, so `History` can show "you rejected this — it would have gained +6.2%" next to "you approved this — it's up 3.1%," across every strategy and every decision, not just the ones that were acted on. This is a deliberate learning tool: the goal is to see whether your own approve/reject judgment is adding value or subtracting it.

**Confidence**
A 0–1 score a `Strategy` attaches to each `Signal` it proposes, expressing how strongly it believes in that trade (continuous, not a binary confident/not-confident flag — e.g. 0.2, 0.4, 0.6...). Drives `Approval mode` when a strategy is set to `auto-above-threshold`.

**Approval mode**
A per-`Strategy` setting controlling whether its `Signal`s need a human's explicit approval before becoming an `Order`. Three values: `manual` (always needs a human click — the default for every strategy until proven), `auto-above-threshold` (auto-approves only when `Confidence` clears a configured bar, else queued for manual approval), `auto` (always auto-approves). Distinct from sizing: approval decides *whether* a trade proceeds; the risk/sizing layer still decides *how much*.

**Kill switch**
The mechanism to immediately halt the bot from submitting further orders. Checked by the execution layer immediately before every order submission.

**Strategy**
A pluggable component that generates `Signal`s from market data, current positions, and account state. v1 ships five concrete strategies (see `docs/adr/0009-v1-strategy-roster.md`), each independently identifiable (every `Signal` carries the `strategy_id` of the `Strategy` that produced it) and independently evaluable (performance is tracked per strategy via its own `Book`, not just in aggregate). The `Strategy` interface is designed to support many more than five; the system was never meant to have only one.

A `Strategy` has `live-enabled` (bool, default `false`): whether it's permitted to place real-money orders at all. This is a one-way-until-you-say-otherwise permission gate, not a phase it moves through — a `Strategy` can always be run against the `demo` `Environment` regardless of its `live-enabled` value; enabling it only additionally allows `live` orders. Promotion is a manual decision the user makes after reviewing the strategy's track record; there's no auto-promotion.

A `Strategy` also has a **style**: `trading` (shorter hold, technical, exits are frequent) or `investment` (longer hold, conviction-based, benefits most from deep `Insight` research). This is descriptive metadata, not a behavioral gate — it informs which strategies get the deeper research tier and how their `Book`'s performance should be read, not a hard rule enforced by the system.

**Trade**
A round-trip: an entry `Order` fill paired with the exit `Order` fill that closed it, carrying a realized P&L. Distinct from `Signal` (the proposal), `Order` (the sized instruction sent to the broker), and `Position` (the current open holding) — a `Trade` only exists once a `Position` has actually been closed out. The backtest engine already has this concept (`TradeRecord`): entry price, exit price, exit reason, quantity, computed P&L. Live/demo trading does not yet have an equivalent persisted record — today it only computes a crude per-fill realized-return proxy (summed across every sell against each sell's own `Signal.reference_price`, not a real FIFO cost basis) for the Strategy detail page's trade log. See `docs/adr/0015-live-trade-ledger.md` for the live-trading `Trade` ledger design.

Booked profit is surfaced two ways once the live `Trade` ledger exists: permanently on `History` next to the closing `Signal` (part of the same "everything about a decided signal stays visible" rule that already applies to reasoning and exit-plan numbers), and as an immediate confirmation the moment a sell executes (e.g. "Sold VUSA.L, booked +£12.40 (+3.1%)").

**Live trading gate**
A single global on/off switch, independent of any per-`Strategy` `live-enabled` flag, that must also be on before Loom will place a single live `Order`. Off by default. Distinct from `Kill switch` (which halts order submission in general, in either `Environment`, and is meant to be flipped in an emergency) — the live trading gate is the deliberate, one-time step of leaving Phase 1 (demo-only) and turning live trading on at all; while it's off, the `live` `Environment` isn't even selectable in the frontend, and the backend independently refuses to run a live trading pass regardless of what the frontend shows.

**Auto-trading gate**
A single global on/off switch controlling whether any `Strategy`'s `Approval mode` is allowed to auto-approve at all. When off, every `Signal` is forced to `pending_approval` regardless of a `Strategy`'s configured `Approval mode` or `Confidence` — a non-destructive circuit breaker, not a mutation of the stored `Approval mode`: turning the gate back on immediately restores each `Strategy`'s own configured behavior with no re-configuration needed.

**Strategy config version**
A `Strategy`'s parameters (thresholds, windows, sizing rules) are not just "whatever's in the code" — each change is a new numbered version. Every `Signal` and every backtest run records which version of its `Strategy` produced it, so a parameter tweak ("move the RSI threshold from 4 to 3") is a traceable, comparable event: you can see exactly what changed and how the strategy's real and backtested performance differed before and after, not just that performance changed at some point.

A version starts as a **draft**: an edited-but-not-yet-official parameter set (still a code/config change per `BACKLOG.md`'s no-code-tuning entry — drafting isn't a UI for editing values, it's a status on a version) that can be backtested like any committed version before the user decides whether to promote it. Promoting a draft is what assigns it its permanent number and makes it the `Strategy`'s current config; an un-promoted draft never produces live `Signal`s. This is distinct from `live-enabled`, which gates a whole `Strategy` for real-money orders, not a single config version.

**Book**
A named, software-level ledger bucket that owns a set of `Position` lots, scoped to one `Environment`, for P&L attribution. Every `Strategy` gets exactly one `Book` per `Environment` (e.g. "Low-Vol Compounder · Live"); there's also a `Manual` `Book` per `Environment` for anything the user trades themselves — directly in Trading 212's own app, or via a manual-trade action in Loom. A position is assigned to a `Book` at the moment `Loom` executes the order that opened it; anything found in the real account that isn't tagged to a `Strategy`'s `Book` (including pre-existing Trading 212 Pies the user already had before adopting Loom) is `Manual` by default, inferred automatically through reconciliation against the live Trading 212 API — the user never has to declare it.

A `Strategy` may generate an advisory `Insight` about a position in *any* `Book`, including `Manual` and other strategies' — but a `Signal` (actionable, approvable) can only ever be proposed against the `Book` owned by the `Strategy` that generated it. Moving a position into a different `Strategy`'s management is a deliberate user action, never something a `Strategy` decides on its own.

Kill switch and account-level exposure/risk limits are computed across the whole `Environment` (every `Book` plus `Manual`), since ISA cash and exposure are genuinely shared — a per-`Book` capital allocation limit is a separate, additional layer on top, not a replacement for the account-level check.

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
