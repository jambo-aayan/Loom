# Context

Domain glossary for the Trading 212 trading bot. This file defines project vocabulary only — no implementation details, no strategy parameters, no architecture decisions (those live in `docs/adr/`).

## Terms

**Signal**
The output of the strategy/idea-generation layer: a proposed trade, before risk/sizing rules are applied. Canonical term — do not use "suggestion" or "trade idea" interchangeably with this; those were used loosely in early discussion but `signal` is the one name for this concept going forward.

A `Signal` becomes a sized `Order` after the risk/sizing layer approves and scales it. An `Order` becomes a `Position` once filled.

**Kill switch**
The mechanism to immediately halt the bot from submitting further orders. Checked by the execution layer immediately before every order submission.

## Open / not yet resolved

- Precise definition of "record" (the bot's own persisted view of positions/trades vs. the Trading 212 API's own history) — under discussion.
- Vocabulary for the strategy's target universe (e.g. "low-volatility large caps and indices") — not yet formalized as a term.
