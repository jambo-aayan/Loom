# Context

Domain glossary for the Trading 212 trading bot. This file defines project vocabulary only — no implementation details, no strategy parameters, no architecture decisions (those live in `docs/adr/`).

## Terms

**Signal**
The output of the strategy/idea-generation layer: a proposed trade, before risk/sizing rules are applied. Canonical term — do not use "suggestion" or "trade idea" interchangeably with this; those were used loosely in early discussion but `signal` is the one name for this concept going forward.

A `Signal` becomes a sized `Order` after the risk/sizing layer approves and scales it. An `Order` becomes a `Position` once filled.

**Kill switch**
The mechanism to immediately halt the bot from submitting further orders. Checked by the execution layer immediately before every order submission.

**Strategy**
A pluggable component that generates `Signal`s from market data, current positions, and account state. The low-volatility large-cap/index approach is one `Strategy`, not the system's only one — the system must support multiple concurrent strategies, each independently identifiable (every `Signal` carries the `strategy_id` of the `Strategy` that produced it) and independently evaluable (performance is tracked per strategy, not just in aggregate).

## Open / not yet resolved

- Precise definition of "record" (the bot's own persisted view of positions/trades vs. the Trading 212 API's own history) — under discussion.
- Vocabulary for the strategy's target universe (e.g. "low-volatility large caps and indices") — not yet formalized as a term.
- Canonical term for LLM-generated advisory content (commentary on a signal, or on-demand research about a stock/macro topic) — needs to be clearly distinguished from `Signal`, since it's non-actionable and must never itself trigger a trade. Proposed: `Insight`. Under discussion.
