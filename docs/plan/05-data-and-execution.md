# 05 · Data and execution

## Source roles

| Source | Used for | Notes |
|---|---|---|
| **Yahoo (yfinance)** | **Primary for LSE** daily and hourly bars and latest price for sizing LSE entries; fundamentals (P/E, yield, debt/equity, sector) | Unofficial and fragile. Batch requests, back off on HTTP 429, and apply the freshness rules below. Decision D25. |
| **Twelve Data** (free: 800 calls/day, 8/min) | **Primary for US stocks only**: daily bars and latest price | Free tier does not cover LSE listings (they need the paid Grow plan; checked 22 Sep 2026, `09-phase0-findings.md`). Not paid for. Supersedes ADR 0008 for LSE. |
| **Trading 212 API** | Orders, positions, cash, `currentPrice` of held instruments, instrument metadata, transaction history (fees, FX) | No general quote feed: prices only for held instruments. Pies endpoints are deprecated; don't use. API keys have per-category scopes; log a 403 with the missing scope. |

Research used Yahoo 60-minute bars (9 per LSE session), the same source live LSE scans now use.

### Symbol mapping

Each Loom instrument has one record mapping it to every external symbol: T212 ticker, Yahoo ticker (e.g. `VUSA.L`), Twelve Data symbol (exchange-qualified, e.g. `NVDA:NASDAQ`), exchange, currency and quoting unit. **Every data request uses an exchange-qualified symbol from this record**; an unqualified symbol like `VUSA` can resolve to a Munich or XETRA listing in EUR. Currency and unit are checked on every response; a mismatch rejects the response. Built in T0.3.

### Freshness rules

- **No data or stale data → no entries** for that instrument in that scan. Record the skip with its reason. Exits are unaffected: they use T212 prices (D15).
- The **hourly scan runs a few minutes after the hour** (e.g. :05) and checks that the latest bar is the bar that just closed before using it. An older latest bar counts as stale.
- Record, per scan, the share of instruments with fresh data. Surfaced later in the health endpoint (T2.8).

## Units and currency

- LSE prices arrive in **GBp (pence)** or **GBP** depending on source and instrument. Normalise to GBP at the data boundary, with the unit recorded alongside every stored price.
- A GBX/GBP mismatch between entry price (Yahoo or Twelve Data) and exit price (T212) would make every stop fire instantly or never. Add a guard: if a live price differs from the lot's entry price by more than 50%, refuse to act and alert.
- Instrument currency comes from **T212 instrument metadata**. LSE lines priced in USD/EUR are excluded from GBP-only universes. Never infer currency from the exchange.

## Universe builder (weekly job)

1. Pull T212 instrument metadata (type, currency, ticker mapping, fractional support, quantity precision).
2. Filter: ETF, GBP/GBp, equity index or sector (maintain an explicit allow/deny list for fund type, seeded from `03-strategy-specs.md`).
3. Liquidity check: hourly bars present for ≥ 80% of LSE trading hours over the last 60 days.
4. Remove Manual-book instruments.
5. Compute instrument groups (correlation ≥ 0.95 over 250 days).
6. Store the result as a versioned universe snapshot; strategies read the latest snapshot.

## Scheduling

All jobs run on Cloud Scheduler and **must be captured in the repo** (e.g. `infra/scheduler.yaml` or a script) so the schedule is reviewable. Every job uses time zone **`Europe/London`**, and each job checks the exchange calendar itself and exits early on a non-trading day (D31).

| Job | When (UK time) | Does |
|---|---|---|
| Daily pre-open scan | 07:45 LSE days | Deep Dip, Crash-buyer (ETFs), Squeeze: evaluate on previous close; refresh Deep Dip targets; create signals; orders at the 08:00 open |
| US pre-open scan | 14:15 NYSE days | Crash-buyer US stocks; orders at the 14:30 open |
| Hourly scan | A few minutes after each hour (e.g. :05) 09:05–16:05 on LSE days, after verifying the just-closed hourly bar is present | Compounder evaluation; submit approved/auto-approved signals |
| Exit enforcer | Every 5 minutes during LSE 08:00–16:30 and NYSE 14:30–21:00 sessions | Read T212 positions + `currentPrice`; sell lots whose target, stop or `exit_by` is hit |
| Signal expiry | With each scan | Expire unapproved signals past their window |
| Reconcile | Hourly | Existing reconciliation; detect drift between Loom ledger and T212 |
| Daily summary | 17:00 LSE days | Record closing Loom value; send summary; start time-exit follow-ups |
| Universe builder | Weekly, Sunday | See above |
| Research insights | As today | Existing |

- Use an exchange calendar library (e.g. `exchange_calendars`) for sessions, holidays and early closes.
- Hourly LSE scans fetch from Yahoo in batches (one request per batch of symbols where possible), with backoff on 429s. Twelve Data's 800 calls/day now only covers US instruments, so there is no data-budget reason for a two-step scan (T4.3 dropped).

### Dead-man's switch
Every scheduled job pings a heartbeat service (e.g. healthchecks.io, free) on success. A missed ping alerts Aayan by email. Configure expected intervals per job.

## Execution

- **Market orders only** (T212 API constraint). Idempotency key per signal (existing, ADR 0014); exits get their own idempotency key per lot and exit reason.
- **Before retrying any order**, query existing orders; never blind-retry.
- **Fill confirmation:** record fill price and quantity from T212 (`filledValue / filledQuantity`); exit levels are computed from the actual fill price.
- **Lots:** each fill creates a Loom lot in the strategy's Book with its exit levels. T212 merges positions per instrument; Loom's ledger is the source of truth for which quantity belongs to which lot.
- **Market hours:** entries and exits are only submitted during the instrument's session.

## Exit enforcer

```
every 5 min during session:
  positions = T212 positions (with currentPrice)
  for each open Loom lot:
    price = positions[lot.instrument].currentPrice (GBP-normalised)
    if price missing or stale → skip, count, alert if persistent
    if halted → skip (log)
    reason = target if price >= lot.target_price
             stop   if price <= lot.stop_price
             time   if now >= lot.exit_by
    if reason → market sell lot.quantity, idempotency key (lot.id, reason)
```

- Squeeze Breakout's volatility exit is emitted by its own daily scan as an exit signal, executed by the same order path.
- **Time-exit follow-up:** when a lot exits on time, store daily (or hourly for Compounder) prices for the next 20 trading days / 45 trading hours and show "what happened next" in History.

## Fee and fill reconciliation

- Daily job pulls T212 transaction history (cursor-paginated; includes fees and FX) and matches it to Loom orders.
- Store per trade: modelled cost, real cost (spread vs reference + fees + FX), and slippage (fill vs price at signal).
- Feeds the "real vs modelled cost" column and the research vs reality dashboard.

## Costs used in research

| Instrument | Round trip |
|---|---|
| GBP ETF, liquid | ~0.08% (spread) |
| GBP ETF, less liquid sector funds | likely 0.1–0.3%; measure in demo |
| US stock | ~0.35% (0.15% FX each way + spread) |
| UK single stock | +0.5% stamp duty on buys: excluded |
