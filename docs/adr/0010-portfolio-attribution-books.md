# 10. Portfolio attribution via software-level Books, not Trading 212 Pies

## Status

Accepted

## Context

With five strategies now in the v1 roster (ADR 0009), we need a way to answer "how is each
strategy actually doing" — e.g. Compounder +20% vs. Harvester -10% — and to define what a
strategy is and isn't allowed to touch, especially given the user's existing, pre-Loom Trading
212 holdings (personal Pies segmented by sector — data companies, semiconductors, ETFs) and the
ability to keep trading manually, in T212's own app or via Loom, alongside the bot.

The obvious first idea was to use Trading 212's own Pies feature for this — one real Pie per
strategy, giving broker-native segmented performance tracking for free. We checked the public
API before committing to this: Trading 212 does expose Pie CRUD endpoints (list/create/update/
delete, under `/api/v0/equity/pies`), but the currently-indexed docs mark at least one Pies
endpoint "(deprecated)", and there's no evidence the order-placement endpoints (market/limit/
stop) can target a specific Pie — Pies appear to be their own target-weight auto-invest
mechanism, not an execution destination for ad hoc orders. Building the safety-critical part of
the architecture (accurate per-strategy attribution, position ownership boundaries) on a beta
API surface already showing deprecation markers repeats the exact risk already rejected when we
declined the community T212 SDKs (ADR referenced in `BACKLOG.md`'s "Community Trading 212 SDKs"
entry) — a single-maintainer, shifting foundation under a live-money-moving path.

## Decision

Portfolio attribution is a software-level concept, tracked entirely in Loom's own database
(already the audit-trail source of truth per the earlier ADRs), not delegated to Trading 212
Pies.

- Introduce **`Book`**: a named ledger bucket owning a set of `Position` lots, scoped to one
  `Environment`. One `Book` per `Strategy` per `Environment`, plus a `Manual` `Book` per
  `Environment`.
- A position is tagged to a `Book` at the moment Loom executes the order that opened it — the
  order itself is a completely normal order against the single real account; no dependency on
  pie-scoped order routing.
- Anything found in the real account that isn't tagged to a `Strategy`'s `Book` — including
  every pre-existing Trading 212 Pie the user had before adopting Loom, and anything traded
  directly in T212's own app or via a manual-trade action in Loom — is `Manual` by default.
  This is inferred automatically by Loom's existing reconciliation against the live T212 API;
  the user never has to declare a manual trade for it to be tracked correctly.
- Per-`Book` P&L is computed from Loom's own ledger (entry price, quantity, current market
  price) — the same computation the backtest engine already needs, just grouped by `Book`
  instead of by instrument or in aggregate.
- A `Strategy` may generate an advisory `Insight` referencing a position in *any* `Book`
  (including `Manual` and other strategies'), but a `Signal` — actionable, approvable — can only
  ever be proposed against the `Book` the generating `Strategy` owns. Reassigning a position to
  a different strategy's management is an explicit user action, never automatic.
- Kill switch and account-level exposure/risk limits are computed across the whole
  `Environment` (every `Book` plus `Manual`), since ISA cash and total exposure are genuinely
  shared regardless of which `Book` a position sits in. A per-`Book` capital allocation limit
  (e.g. "Compounder can deploy at most £2,000") is an additional layer on top, not a substitute.

Mirroring each `Book` as a real Trading 212 Pie (so it's also visible natively in T212's own
app) is a plausible later nice-to-have, tracked in `BACKLOG.md` — not the backbone, and not
built for v1.

## Consequences

- No new external dependency or testing seam: `Book` attribution lives entirely in Loom's
  existing database and reconciliation logic.
- The user's existing sector Pies (data companies, semiconductors, ETFs) stay exactly as they
  are — Loom is aware of their balances for account-level risk/exposure math, but never
  proposes or executes trades against them unless the user explicitly moves a position into a
  strategy's `Book`.
- The Overview/Performance UI needs a per-`Book` breakdown, not just an aggregate account view —
  this is new surface area beyond what the current dashboard mockups show and should be folded
  into the next design pass.
- If Trading 212 later stabilizes and extends the Pies API (e.g. order-to-pie routing becomes
  documented and non-deprecated), revisit this decision — the `Book` abstraction was kept
  broker-agnostic enough that swapping its storage/visualization to real Pies later wouldn't
  require changing the `Strategy`/`Signal`/`Insight` model above it.
