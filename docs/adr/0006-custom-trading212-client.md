# Custom Trading 212 client, not a community SDK

We write and maintain our own thin Trading 212 API client rather than depending on a community package (`python-trading212`, `t212-api`, or similar).

## Considered options

Both existing community SDKs were audited and rejected: `python-trading212` is stale (no activity in ~9 months) with no tests and no rate-limit/pagination handling; `t212-api` is better engineered (typed, tested, handles rate-limit headers and pagination) but is brand new — 5 commits, 1 star, single author, no track record. Neither has the adoption or audit trail to justify trusting it with a Live, money-moving API key. We're borrowing `t212-api`'s rate-limit/pagination patterns as a design reference without taking it as a dependency.
