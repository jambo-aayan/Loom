# Context

Domain glossary for the Trading 212 trading bot. This file defines project vocabulary only — no implementation details, no strategy parameters, no architecture decisions (those live in `docs/adr/`).

## Terms

**Signal**
The output of the strategy/idea-generation layer: a proposed trade, before risk/sizing rules are applied. Canonical term — do not use "suggestion" or "trade idea" interchangeably with this; those were used loosely in early discussion but `signal` is the one name for this concept going forward.

A `Signal` becomes a sized `Order` after the risk/sizing layer approves and scales it. An `Order` becomes a `Position` once filled.

A `Signal`'s lifecycle: `proposed` → (`auto-approved` or `pending-approval`, per its `Strategy`'s `Approval mode`) → (`approved` or `rejected`) → `executed`.

**Confidence**
A 0–1 score a `Strategy` attaches to each `Signal` it proposes, expressing how strongly it believes in that trade (continuous, not a binary confident/not-confident flag — e.g. 0.2, 0.4, 0.6...). Drives `Approval mode` when a strategy is set to `auto-above-threshold`.

**Approval mode**
A per-`Strategy` setting controlling whether its `Signal`s need a human's explicit approval before becoming an `Order`. Three values: `manual` (always needs a human click — the default for every strategy until proven), `auto-above-threshold` (auto-approves only when `Confidence` clears a configured bar, else queued for manual approval), `auto` (always auto-approves). Distinct from sizing: approval decides *whether* a trade proceeds; the risk/sizing layer still decides *how much*.

**Kill switch**
The mechanism to immediately halt the bot from submitting further orders. Checked by the execution layer immediately before every order submission.

**Strategy**
A pluggable component that generates `Signal`s from market data, current positions, and account state. The low-volatility large-cap/index approach is one `Strategy`, not the system's only one — the system must support multiple concurrent strategies, each independently identifiable (every `Signal` carries the `strategy_id` of the `Strategy` that produced it) and independently evaluable (performance is tracked per strategy, not just in aggregate).

A `Strategy` has `live-enabled` (bool, default `false`): whether it's permitted to place real-money orders at all. This is a one-way-until-you-say-otherwise permission gate, not a phase it moves through — a `Strategy` can always be run against the `demo` `Environment` regardless of its `live-enabled` value; enabling it only additionally allows `live` orders. Promotion is a manual decision the user makes after reviewing the strategy's track record; there's no auto-promotion.

**Environment**
`demo` or `live` — which Trading 212 account (and therefore which base URL/API key) a given `Signal`, `Order`, or `Position` belongs to. Not a phase or a one-time deployment setting: both environments are always available side by side, and the UI has an explicit switch between them (comparable to an exchange's testnet/live toggle), so the user can test any `Strategy` against `demo` at any time independent of what's currently running on `live`.

**Insight**
LLM-generated advisory content — commentary on why a specific `Signal` fired, or on-demand research about a stock/macro topic. Deliberately distinct from `Signal`: an `Insight` is never actionable on its own and can never directly trigger an `Order`; it only informs a human or, if a future `Strategy` implementation chooses to use one as an input, that `Strategy`'s own signal generation (still subject to the same risk/sizing and approval gates as any other `Signal`).

## Open / not yet resolved

- Vocabulary for the strategy's target universe (e.g. "low-volatility large caps and indices") — not yet formalized as a term.
