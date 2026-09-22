# 04 · Sizing, the budget fence, and safety

## The budget fence

Loom operates inside Aayan's T212 Stocks ISA, which also holds his personal investments (~£6.5k). Loom must be unable to affect them.

| Rule | Implementation |
|---|---|
| **Loom budget** | Setting, £1,000 initially. Changed only by Aayan in Settings. |
| **Loom value** | `Loom cash + Σ market value of Loom lots`. This, not the ISA total, is the base for all sizing, limits and P/L. |
| **Loom cash** | `Loom budget + realised Loom P/L (if reinvest on) − cost of open Loom lots`. Tracked in Loom's own ledger. |
| **Spendable cash** | `min(actual ISA free cash, Loom cash − cash reserve)`. Loom never spends ISA cash beyond its own. |
| **Only sell own lots** | Every sell path (exit enforcer, strategy exits, manual close) sells exactly the quantity of a Loom lot, never more. Sell requests are validated against the Book ledger before submission. |
| **Exclude personal holdings** | Any instrument in the Manual book is removed from every strategy's universe at runtime. T212 merges positions per instrument, so co-holding would make Loom sells ambiguous. |
| **No top-ups** | If Loom value falls, it trades with less. Budget increases are a deliberate Settings action (logged). |
| **Reinvest profits** | Toggle. On: realised gains increase Loom cash. |

## Sizing

### Sleeves and slots (Balanced default)

| Strategy | Sleeve | Slots | Per trade at £1,000 |
|---|---|---|---|
| Deep Dip | 35% | 3 | ~£115 |
| Compounder | 30% | 3 | £100 |
| Crash-buyer | 20% | 2 | £100 |
| Squeeze Breakout | 15% | 2 | £75 (shadow: notional only) |

`per_trade_£ = Loom value × sleeve% ÷ slots`, computed at submission time.

### Order of checks for every entry

1. Not paused, not halted (pause/halt state checked immediately before submission, as the kill switch is today)
2. Strategy status is Active (Shadow records the signal and its would-be outcome, no order)
3. Strategy has a free slot
4. No existing lot of this strategy in the same instrument group
5. Instrument group cap has room after this trade (across all strategies)
6. Single-stock cap (US stocks, 5%)
7. Total invested ≤ `100% − cash reserve`
8. **Spendable cash re-read now** (after any order placed earlier in this pass) ≥ trade size
9. Trade size ≥ minimum trade (£25). If any cap would shrink it below that: **skip, don't shrink**.

Every skip is recorded with its reason (`no_slot`, `group_cap`, `stock_cap`, `exposure_cap`, `cash`, `below_minimum`, `paused`, `personal_holding`) and shown in History → Skipped signals.

### Ranking when there are more signals than room
Process signals within a pass in order of **most negative z-score first** (deepest dip). Squeeze signals rank after dips. Do not use the uncalibrated confidence number.

### Quantity
`quantity = per_trade_£ / fresh_price`, rounded down to the instrument's allowed precision from T212 metadata. Fractional quantities where T212 allows; instruments that don't support fractional trading and whose share price exceeds the per-trade size are excluded from the universe.

`fresh_price` is fetched at submission, not taken from signal generation (fixes the stale `reference_price` issue in BACKLOG): T212 `currentPrice` if the instrument is already held in the account, otherwise the latest quote from the instrument's primary source (Yahoo for LSE, Twelve Data for US; D25), normalised to GBP. No fresh price → no entry.

### Instrument groups
- Built automatically: instruments whose daily returns over the last 250 trading days correlate ≥ 0.95 are in the same group (connected components). Recomputed weekly; manual overrides stored separately and applied on top.
- Expected examples: S&P 500 trackers (VUSA, CSP1, VUAG, IUSA, SPXP), world trackers (VWRL, VWRP, SWLD, IWRD, HMWO).
- **Group cap:** total Loom exposure to one group across all strategies ≤ 25% of Loom value (Balanced).
- **One per group per strategy:** a strategy never holds two instruments from the same group.

## Risk profiles

| Setting | Conservative | **Balanced (default)** | Aggressive |
|---|---|---|---|
| Cash reserve | 20% | 10% | 5% |
| Group cap | 20% | 25% | 40% |
| Slots (DD / Comp / Crash / Squeeze) | 3/3/2/2 | 3/3/2/2 | 2/2/1/1 |
| Daily loss limit (pauses) | 2% | 3% | 5% |
| Budget kill switch (pauses) | −10% | −15% | −25% |
| Single US stock cap | 3% | 5% | 8% |

Each value remains individually editable; editing one marks the profile "Custom". Demo and live must run the same profile for the demo gate to count (D23).

## Pause and Halt

| State | Entries | Exits (enforcer + strategy exits) | Triggered by |
|---|---|---|---|
| **Normal** | Yes | Yes | — |
| **Paused** | Blocked | **Run** | Header button; daily loss limit; budget kill switch; missed-data safety checks |
| **Halted** | Blocked | **Blocked** | Manual only, Settings, typed confirmation |

- Stored as DB events (like `KillSwitchEvent` today), per environment, with who/what triggered it and why.
- Checked immediately before every order submission.
- Resuming from an automatic pause requires a manual action; the UI shows the reason.
- The existing "kill switch" maps to **Halt**. Update `CONTEXT.md`.

## Daily loss limit and budget kill switch

- Computed from **live Loom value** using T212 `currentPrice` for held lots (fixes cost-basis blind spot).
- **Snapshot poisoning fix:** the day's starting value is taken from the previous trading day's closing Loom value (recorded by the daily summary job), not from whichever check runs first. If the implied intraday move exceeds 30%, treat it as a data error: do not pause, alert Aayan instead.
- Budget kill switch: pause when Loom value < `(1 + threshold) × Loom budget at last budget change`.

## Approval modes

- Per strategy: Manual / Auto above a strength threshold / Auto. Global auto-approval gate overrides all.
- Compounder signals expire at the end of the next hourly bar; daily strategies' signals expire at that session's close.
- Recommended progression: Manual for the first ~10 demo trades per strategy, then Auto for the Compounder (its signals arrive during Aayan's working day).

## Capital lending (Phase 4, not in the first build)

- When the Crash-buyer holds fewer lots than its slots, up to **50% of its idle sleeve** may be used by Deep Dip and the Compounder (split pro rata to their sleeves).
- When a borrowed-funded lot closes and the Crash-buyer has an active signal waiting, the proceeds are reserved for the Crash-buyer first.
- Why it works: the market filter switches dip strategies off exactly when the Crash-buyer switches on.
- Prototype the state model before building (use `prototype` skill).

## Invariants (each needs a test)

1. No order is submitted while Halted. No entry is submitted while Paused.
2. Exits are submitted while Paused.
3. A sell never exceeds the quantity of the Loom lot it closes.
4. No order for an instrument in the Manual book is ever placed by a strategy.
5. Σ cost of open Loom lots ≤ Loom cash available at each submission; two entries in one pass cannot double-spend.
6. Group cap and one-per-group hold across strategies after every fill.
7. Every Loom lot has `target_price`, `stop_price`, `exit_by` set within the same transaction as its fill is recorded.
8. Hold periods use trading days/hours from the exchange calendar.
9. Prices crossing the data boundary are in GBP (not GBp); a unit mismatch fails loudly.
10. Shadow strategies and shadow configs never create orders.
11. Live environment is never touched unless the live-trading gate is on (existing).
