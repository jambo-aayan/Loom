# 14. T212 order idempotency: rely on the DB-level guard, drop the client-side heuristic

## Status

Accepted

## Context

Trading 212's `POST /equity/orders/market` endpoint is explicitly documented as not idempotent:
there is no client-supplied idempotency key it will honor, and a retried or duplicated request
can place a second real order. Loom's execution layer needs some protection against submitting
the same `Order` twice — most realistically from a network timeout or a retried trading pass,
not from a user action (each `Signal` can only be approved once; the approval endpoint itself
already guards against double-submission at that layer).

Before this ADR, `t212_client.py` had grown a client-side heuristic on top of this: a
fabricated `clientOrderId`-style value and a pre-check that tried to detect a likely-duplicate
order before sending. This never actually worked as real idempotency, because T212's API does
not accept or honor any client-supplied order identifier — the heuristic could only reduce, not
eliminate, duplicate submissions, while adding code that looked like a real safety mechanism.

## Decision

- **Drop the client-side heuristic entirely.** No fabricated `clientOrderId`, no pre-submission
  duplicate-check call against T212.
- **Rely solely on the existing DB-level guard**: `Order.idempotency_key` already carries a
  unique constraint, generated deterministically from the originating `Signal` before Loom ever
  calls T212. A second attempt to create an `Order` for the same `Signal` fails at the database
  layer before any HTTP request is made — this is real, unconditional protection against Loom
  itself double-submitting, independent of anything T212's API does or doesn't support.
- **Document, rather than paper over, the residual gap**: the DB guard only prevents Loom from
  *starting* a second submission for the same `Signal`. It does not cover the case where a
  single submission's HTTP request has actually reached T212 and executed, but the response
  never reaches Loom (a network timeout, a dropped connection, a process restart mid-request).
  In that scenario, the `Order` row is left in `submitted` status indefinitely — not a silent
  duplicate order (nothing retries it), and not a false failure either (the order may well have
  filled) — it is a stuck record that needs reconciliation against T212's own order/position
  state to resolve.

## Consequences

- `t212_client.py` is simpler and no longer contains a safety mechanism that couldn't actually
  deliver on its name.
- The real remaining risk is a stuck `submitted` `Order` after a timeout, not a duplicate order.
  This is a reconciliation problem (compare Loom's `submitted` orders against T212's actual
  order/fill history and resolve the mismatch), not an idempotency problem — v1 does not yet ship
  automatic reconciliation for this specific case; a `submitted` order that never resolves is
  visible in the data (status never advances to `filled`) and can be checked manually against the
  T212 app during Phase 1's demo-only operation, where the operator is actively watching. This is
  an accepted gap for v1, not a design that was expected to be airtight — building automatic
  reconciliation is future work, not blocking Phase 1's demo-only launch.
