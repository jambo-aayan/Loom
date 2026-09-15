# UI and Data-Surface Audit

Fourth part of the gap analysis: what the dashboard shows versus what it should show, measured
against the committed prototype (`design/prototype/loom-prototype.html`), the 20-artboard canvas
(`design/canvas/`), and the requirements raised while reviewing the live demo app.

Companions:
- `docs/strategy-and-universe-gap-analysis.md` — strategy logic and the instrument universe
- `docs/spec-vs-implementation-audit.md` — conformance against CONTEXT.md, issue #1, the ADRs
- `docs/platform-and-backtest-audit.md` — security, backtest fidelity, calibration

---

## 1. Requirements raised from the live app

Observed state of Overview in demo: a `Cash (demo)` figure of £4,007.34, one `Books` row
(Low-Vol Compounder · demo, £986.24, −£6.42 / −0.6%), and two `Positions` rows showing only
ticker, unit count and average price.

### 1.1 No total portfolio value, and no change figure

The header shows **cash only**. There is no account total (cash + market value of all positions)
and no percentage change.

This isn't a rendering omission — the API doesn't return it. `OverviewOut`
(`loom/api/schemas.py:147`) is `{environment, cash, positions, book_pnl}`. There is no
`total_value`, no `total_pnl`, and no time-series to compute a change against.

Every input already exists inside the `overview` handler: it fetches `broker.get_positions()`,
builds a `current_prices` map from T212's live `currentPrice`, and computes per-book market value
via `book_pnl`. The total is a sum of values already in hand at that point — it's simply never
assembled or returned.

The prototype had this, and had it as the primary element: a portfolio figure at 38px, a change
line (`+£186.40 · +2.2% this month`), and an equity sparkline beneath it
(`design/prototype/loom-prototype.html:394-407`). The build regressed to cash-only.

### 1.2 Positions carry no price, value, or P&L

`PositionOut` (`schemas.py:128`) is `{book_id, book_name, strategy_key, instrument, quantity,
average_price}`. No `current_price`, no `market_value`, no `unrealized_pnl`.

So a position renders as "VWRL.L · 3.5824 units · avg £138.50" and the user cannot tell from the
Overview whether it is up or down. The `current_prices` map needed to fix this is built three
lines above the loop that constructs these objects, and used for `book_pnl`, but never attached
to the individual positions.

Trading 212's own positions list — the stated reference — shows per-holding value and
gain/loss in both absolute and percentage terms. That is the target shape.

### 1.3 Positions don't show their exit plan

Once a signal becomes a position, its exit plan disappears from the UI entirely.

The Approvals page **does** show it — `frontend/app/approvals/page.tsx:146-148` renders
`target {profit_target_pct}` and `stop {stop_loss_pct}` on each pending signal. But nothing
carries that forward: `PositionOut` has no `exit_plan` field, so an open position gives no
indication of what it's waiting for or where it will be sold.

This compounds the enforcement gap from the first document. For Trend Follower and Volatility
Breakout the exit plan isn't enforced live at all — so a position shows no exit *and* has no
exit. For the other three the plan is enforced, but invisibly.

Both halves need fixing, and in that order: enforce it, then show it.

### 1.4 Commissions and fees are not modelled anywhere

The `Order` model (`loom/models.py:187`) stores `quantity`, `fill_price`, `broker_order_id`,
`submitted_at`, `filled_at` — and no cost field of any kind. No commission, no FX fee, no spread,
no total consideration.

The consequence is that **every P&L figure in the system is gross**:

- `ClosedTrade.pnl` = `(exit_price - entry_price) * quantity` (`trade_reconstruction.py:29`)
- `book_pnl` — the −£6.42 (−0.6%) on the Overview screenshot
- every evaluation metric built on those trades (win rate, profit factor, expectancy, Sharpe)
- the backtest engine (covered separately as §2.1 of the platform audit)

For this account specifically: T212 charges **0.15% FX conversion** on non-GBP instruments. The
current universe is half USD (TSLA, NVDA), and the live ISA holds QCOM, AAPL and META. That is
0.3% per round trip, before spread — against a Compounder profit target of 4% and a Harvester
target of 6%.

Fixing this properly has three parts, and they're separable:
1. Capture the actual fee from T212's fill response into a new `Order` column (the API returns
   more on a filled order than the client currently reads).
2. Subtract it everywhere P&L is computed from real fills.
3. Add a modelled cost assumption to the backtest engine so historical results are comparable to
   live ones.

### 1.5 The trading pass should run on its own

The infrastructure for this exists — `infra/gcp/setup.sh` provisions a `loom-trade-pass` Cloud
Scheduler job at `0 8 * * 1-5` (weekdays 08:00 UTC), plus screening, research and reconcile jobs.

If passes only ever happen when the "Run trading pass" button is pressed, the most likely
explanation is that `setup.sh` was never applied to the project, or the scheduler job exists but
its runs are failing. Both are checkable:

```
gcloud scheduler jobs list --location <region> --project <project>
gcloud run jobs executions list --job loom-trade-pass --region <region>
```

Worth settling before changing anything, because the two cases lead to different work: one is
"run the script", the other is "debug the job". A third possibility — that it runs fine and
produces nothing — is the one the first document's lookback bug predicts, and would leave no
trace in the UI at all.

Separately, once it is running: 08:00 UTC weekdays is a single daily pass pinned to `demo`. Whether
that cadence is right is a real question — the strategies are patient by design (ADR-0002), but a
single daily pass means an exit signal can be up to 24 hours late, which matters more now that
stops are the most common exit.

---

## 2. Regressions against the committed prototype

`design/HANDOVER.md` §2b lists what the prototype does. Checked against the build:

| Prototype behaviour | Built? |
|---|---|
| Navigation across all 7 pages | Yes |
| Light/dark theme toggle, persisted | Yes |
| Strategy detail: trade log + cumulative-return chart | Yes |
| Approve/Reject mutating state, writing to History | Yes |
| Kill switch global | Yes |
| **Portfolio total + change + equity sparkline on Overview** | **No** |
| **"Awaiting your approval" count + Review-queue CTA** | **No** |
| **Per-position change %** | **No** |
| **Recent-signals list on Overview** | **No** |
| **Demo/Live switch** | **No** (see spec audit §2.2) |
| **Per-strategy threshold sliders in Settings** | **No** |
| **Risk-limits card in Settings** | **No** |
| Nav badge counts for pending approvals | No |
| Per-trade return bar chart on Strategy detail | No |

### 2.1 Settings is the largest regression

The prototype's Settings had a Risk limits card — max position size, max total exposure *with
current utilisation* ("80% of portfolio · at 61%"), daily loss limit in £, and a halt-on-breach
toggle — plus a Notifications card and live threshold sliders per strategy.

The built Settings has three global toggles (live trading, auto trades, kill switch) and a
strategy list where `approval_mode`, `approval_threshold` and `notify_threshold` render as
**read-only text**: `Approval mode: {s.approval_mode} · threshold {s.approval_threshold} · notify
{s.notify_threshold}`.

Only `live_enabled` is editable. Yet `PATCH /strategies/{id}` already accepts all four fields
(`StrategyUpdate`, `schemas.py:20`). So the backend supports what the prototype designed and the
UI simply doesn't expose it — approval mode and both thresholds currently cannot be changed
without calling the API by hand.

This is the cheapest high-value UI work available: the endpoint exists, the prototype specifies
the control, and the missing capability is one a user needs constantly.

The risk-limits half is not as cheap, because those limits genuinely aren't configurable anywhere
(spec audit §2.3) — the UI can't display or edit what the backend hardcodes.

### 2.2 Overview is missing its primary element

Everything in §1.1-1.3 above is a restatement of this: the prototype's Overview led with
portfolio value, change, and an equity curve, then showed an approvals CTA, strategy chips,
positions with per-position change, and recent signals. The build has cash, books, and bare
positions.

The design tokens and layout are already committed in `design/prototype/loom-prototype.html` and
`design/canvas/Main.dc.html` / `Mobile.dc.html`, so this is a matter of building what was already
designed, not designing it again.

---

## 3. A confirmation from the live ISA

The live Stocks ISA screenshot shows holdings across pies — ETF, SemiConductors, Companies, Copy
of Pelosi Tracker, Data — plus direct holdings in Qualcomm, Apple and Meta Platforms, at a total
account value of £5,905.83.

**None of those instruments are in `LOOM_TO_T212`**, which contains exactly four entries:
`VUSA.L`, `VWRL.L`, `TSLA`, `NVDA`.

This makes the `Manual` book finding concrete rather than theoretical. `from_t212` raises
`UnmappedInstrumentError` on any unmapped ticker, with no handling at
`t212_client.py:168`. The moment Loom is pointed at this live account:

- `broker.get_positions()` raises
- the Overview endpoint 500s (it calls `get_positions()` before anything else)
- reconciliation cannot run
- the `Manual` book — whose entire purpose per ADR-0010 is to pick up exactly these pre-existing
  sector pies — sees nothing

Demo works today only because Loom itself bought both instruments in it, and both happen to be in
the map.

This should be treated as a live blocker, not a backlog item: it fails closed on the first real
request, and it fails on the account the whole `Book` model was designed around.

---

## 4. Where this sits against the rest

Ordering the four documents together, by what blocks what:

1. **Public unauthenticated API** (platform audit §1.1) — before any live exposure.
2. **Unmapped-ticker handling** (§3 above) — before pointing Loom at the live ISA at all.
3. **Lookback in bars + live exit enforcement** (gap analysis B1, C1/C2) — before any strategy
   behaviour can be judged.
4. **Confirm the scheduler is actually running** (§1.5) — cheap, and determines whether the
   silence is a bug or an absence.
5. **Fees captured and subtracted** (§1.4) — before any P&L number is trusted, live or backtested.
6. **Overview data surface** (§1.1-1.3) — total value, per-position price/value/P&L, exit plan
   on positions. All additive to `OverviewOut`/`PositionOut`, all from data already fetched.
7. **Settings threshold controls** (§2.1) — endpoint already exists.
8. Remaining prototype regressions, then per-strategy logic.

Items 6 and 7 are the ones that will make the app feel finished, and neither is blocked by
anything above it — they can run in parallel with the strategy work.
