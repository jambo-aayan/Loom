# Custom Trading 212 client, not a community SDK

We write and maintain our own thin Trading 212 API client rather than depending on a community package (`python-trading212`, `t212-api`, or similar).

## Considered options

Both existing community SDKs were audited and rejected: `python-trading212` is stale (no activity in ~9 months) with no tests and no rate-limit/pagination handling; `t212-api` is better engineered (typed, tested, handles rate-limit headers and pagination) but is brand new — 5 commits, 1 star, single author, no track record. Neither has the adoption or audit trail to justify trusting it with a Live, money-moving API key. We're borrowing `t212-api`'s rate-limit/pagination patterns as a design reference without taking it as a dependency.

## Rate limiting, corrected against the real API (Sep 2026)

Confirmed live against T212's demo API, not just from docs: `x-ratelimit-reset` is a **Unix epoch
timestamp** for when the window resets, not a countdown of seconds — an earlier version of
`Trading212Client._pace_from_headers` slept on the raw header value directly, which meant sleeping
until that epoch arrives in real wall-clock time (decades away), hanging the request indefinitely
the first time any endpoint's limit was actually hit. Fixed to compute the delta from `time.time()`
and cap it.

Per-endpoint limits differ and are tight: `/equity/positions` was observed at `limit=1, period=1`
(one request per second); `/equity/account/summary` at `limit=1, period=5`. A request can still
come back `429` even when client-side pacing looked clear going in, since pacing only reacts to the
*previous* response's headers, not the live state at send time — `_request` now retries with
backoff on an actual 429 rather than letting `raise_for_status()` propagate it straight up as an
unhandled error. Callers that loop over several books/strategies in one pass should still minimize
real call volume rather than relying on retries alone (see `trading_pass.run_trading_pass`, which
fetches `get_cash()` once per pass instead of once per book) — retries buy resilience, they don't
turn a tight limit into a loose one.
