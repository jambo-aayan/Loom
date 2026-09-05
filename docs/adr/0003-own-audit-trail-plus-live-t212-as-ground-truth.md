# Own audit-trail database, Trading 212 stays ground truth for positions/history

The system maintains its own database recording every `Signal` generated (including ones never acted on, with the reasoning behind them), every `Order` submitted with its idempotency key, and `Kill switch` events — an audit trail of the bot's own decisions. It does not duplicate Trading 212's own records of positions and order history; those are always fetched live from the Trading 212 API, which remains the single source of truth for "what actually happened."

## Considered options

Mirroring T212's positions/history into our own DB was considered, but rejected: it would require reconciliation logic to keep two records in sync, and T212's API is already authoritative for that data. The bot's own decisions (why a signal fired, why it was approved or rejected) are the one thing T212's API can't tell us, so that's what we persist.
