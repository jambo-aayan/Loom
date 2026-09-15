# Platform, Security, and Backtest-Fidelity Audit

Third and final part of the gap analysis, covering areas the first two didn't reach:
API security and deployment posture, backtest realism, and confidence calibration.

Companions:
- `docs/strategy-and-universe-gap-analysis.md` — strategy logic and the instrument universe
- `docs/spec-vs-implementation-audit.md` — conformance against CONTEXT.md, issue #1, and the ADRs

---

## 1. Security

### 1.1 CRITICAL — The deployed API is public and unauthenticated

There is no authentication anywhere in the backend. No auth dependency, no API key check, no
session, no middleware. Every router takes `Depends(get_db)` and nothing else.

Combined with the deployment:

- `infra/gcp/setup.sh:141` deploys the Cloud Run service with `--allow-unauthenticated`
- `loom/api/main.py` sets `CORSMiddleware` with `allow_origins=["*"]`, `allow_methods=["*"]`,
  `allow_headers=["*"]`

So anyone who knows (or finds) the Cloud Run URL can reach every endpoint. And because there are
no credentials involved, a plain `fetch()` from any web page in any browser also works — the
permissive CORS config means a page the user merely visits could drive it.

The reachable chain is complete:

| Step | Endpoint | Effect |
|---|---|---|
| 1 | `POST /settings/live-trading-gate/enable` | turns on live trading globally |
| 2 | `PATCH /strategies/{id}` | sets `live_enabled: true`, `approval_mode: "auto"` |
| 3 | `POST /settings/kill-switch/resume` | clears the kill switch |
| 4 | `POST /trading-pass/run?environment=live` | runs a live pass; auto-approved signals execute |

`StrategyUpdate` (`loom/api/schemas.py:20`) accepts exactly `live_enabled`, `approval_mode`,
`approval_threshold` and `notify_threshold`, and `update_strategy` `setattr`s each one with no
validation beyond the Pydantic type. Every one of the safety controls in CONTEXT.md — the kill
switch, the live trading gate, the auto-trading gate, per-strategy `live-enabled` — is
individually switchable by an anonymous caller.

The controls themselves are correctly implemented and correctly checked in the execution path.
They simply have no access control in front of them.

Mitigating factors, such as they are: the live T212 credentials must be configured for step 4 to
reach a real broker, and the live trading gate is off by default. Neither is a defence — steps 1
to 3 exist precisely to flip those.

### 1.2 ADR-0004 does not actually cover this

ADR-0004 says:

> v1 has no authentication and no per-user data isolation — it's built for one account (the
> founder's). This was a deliberate choice against building real multi-tenancy...

That paragraph reasons entirely about **multi-tenancy** — user accounts, per-user isolation,
billing. "No user accounts because there is one user" is a sound conclusion. "Therefore the
money-moving API needs no access control on a public URL" does not follow from it, and the ADR
never considers the question.

This is worth resolving as a decision, not just a patch: single-user does not mean
single-visitor. The cheapest adequate answer is probably removing `--allow-unauthenticated` and
putting the frontend's calls behind a shared secret or Google IAP, but it is a real decision with
a real ADR attached, and it should be made before the live trading gate is ever switched on.

### 1.3 Signed action links are the one path that got this right

`SignedActionLink` (story 64) implements single-use, short-expiry, signed tokens for
approve/reject from email, and story 65's requirement that the link only ever invokes the same
approval path with the full risk re-check. That path is careful.

The irony is that the emailed link — the one entry point designed to be used by someone not
logged in — is the *only* authenticated one, while the dashboard API it protects is wide open.

---

## 2. Backtest fidelity

### 2.1 There is no transaction-cost model at all

A grep for `commission|slippage|spread|fee` across `loom/` returns nothing but an unrelated
comment. Backtests fill at the bar close, in full, instantly, for free.

Real costs for this account:

- **Bid-ask spread** on every entry and exit, on every instrument.
- **Trading 212's 0.15% FX conversion fee**, charged on every trade in a non-GBP instrument —
  which is `TSLA` and `NVDA`, half the universe. That is 0.3% per round trip before any spread.

Measured against the strategies as configured, this is not a rounding error:

| Strategy | Trades (6y) | Profit target | Round-trip FX cost as % of target |
|---|---|---|---|
| Volatility Harvester | 238 | 6% | ~5% of the target, per trade, on US names |
| Low-Vol Compounder | 157 | 4% | ~7.5% of the target |
| Volatility Breakout | 20 | (no target; stop 6%) | — |

Harvester's measured result was a 59% win rate and roughly zero return *before costs*. Adding
realistic costs to 238 trades moves that from "no edge" to "reliably negative." The backtest
currently cannot show that, which makes it actively misleading for exactly the high-turnover
strategies where costs matter most.

Note this also interacts with the FX gap in the companion document: the system has no concept of
currency at all, so it cannot currently even identify which instruments incur the FX fee.

### 2.2 Entries fill at the same close the signal was computed from

In `run_backtest`, the strategy is handed history truncated to day `d` — including day `d`'s
close — and any resulting order fills at `bar.close` for that same day `d`.

The no-lookahead rule (story 43) is satisfied in the sense the tests check: the strategy never
sees data beyond the simulated now. But the fill is still at a price that was only knowable at
the moment the bar closed, and a real scheduled pass at 08:00 UTC cannot trade at that day's
close. A live pass computes a signal from yesterday's close and fills at today's open or later.

The realistic model is to fill at the *next* bar's open. The current model systematically
flatters any strategy whose entry trigger is itself a same-day price event — which is all five,
and most severely Volatility Breakout, whose entry condition is literally "today's close broke
out," filled at that same close.

### 2.3 `total_return_pct` and `benchmark_return_pct` are fractions, not percentages

`engine.py:247-248` compute `(final_equity - starting_capital) / starting_capital` and store it
under a `_pct` name. A 2.0 in that field means +200%, not +2%.

Nothing currently multiplies by 100 before display, so any consumer reading it as a percentage —
a human included — is off by 100x. This is what made the first pass at these backtests look like
every strategy returned ~0.1% when the real figure was ~10%.

---

## 3. Confidence calibration

### 3.1 Running any backtest silently overwrites live signal confidence

`POST /backtests` (`loom/api/routers/backtests.py:66`) ends with an unconditional:

```python
calibration.save_calibration(session, strategy.id, version.id, result.trades, run.id)
```

`save_calibration` upserts on `(strategy_id, config_version_id)`. `trading_pass.py:264` then reads
that same row to replace each live entry signal's confidence.

So an exploratory backtest from the dashboard — over a two-month window, or over a custom
`universe` that live trading doesn't even use (`body.universe` is caller-supplied) — permanently
replaces the calibration that governs live signal confidence for that strategy's promoted config
version. There is no confirmation, no versioning of calibrations, and nothing in the UI that
indicates it happened.

Exploring should not mutate production behaviour. Calibration should be an explicit action, or at
minimum scoped to backtests whose window and universe match live.

### 3.2 No minimum sample size — a single winning trade yields confidence 1.0

`compute_buckets` records `num_trades` per bucket. `lookup_confidence` never consults it:

```python
for bucket in buckets:
    if bucket["min"] <= strength <= bucket["max"]:
        return bucket["win_rate"]
```

A bucket containing one trade that happened to win has `win_rate == 1.0`. The default
`approval_threshold` is **0.8** (`models.py:94`), so under `auto-above-threshold` that signal
auto-approves and executes with no human in the loop.

`lookup_confidence` also extrapolates out-of-range strengths to the nearest edge bucket — and the
edge buckets are exactly where sample counts are thinnest. A live signal stronger than anything
in the backtest inherits the top bucket's win rate, which may rest on one or two trades.

This is the most direct route in the codebase from "thin data" to "real order, no human." A
minimum-trades floor, below which the strategy's own heuristic confidence is kept instead, is the
obvious guard.

### 3.3 Calibration is in-sample by construction

Buckets are computed from a backtest over a window, then applied to live signals. There is no
train/test split, no walk-forward validation, and no purging.

ADR-0009 specifies this design directly ("use the realized win rate/expectancy in that bucket as
the confidence for a live signal landing in the same bucket"), so this is a design risk rather
than an implementation defect. But it should be recorded as one: win rates measured on the same
data used to choose the parameters are biased upward, and that bias flows straight into the
number that decides whether a trade is auto-approved.

---

## 4. Verified sound

Recorded so the three documents aren't read as uniformly negative. Checked and found correct:

- **Alembic migrations cover all 14 models** — no schema drift between `models.py` and
  `alembic/versions/`.
- **`init_db`'s `create_all` is correctly guarded to sqlite**, with the production incident that
  motivated the guard documented inline (a Cloud Run first request creating the schema before
  `alembic upgrade head` could run).
- **Test coverage is genuinely broad**: 58 test files, including a shared strategy contract suite
  run against all five strategies, backtest no-lookahead tests, T212 client tests against
  recorded fixtures, and API-level tests through real routing.
- **The T212 client** does what ADR-0006 and stories 8-10 require: idempotency keys, rate-limit
  pacing off `x-ratelimit-*` headers, and full request/response logging.
- **The kill switch, live trading gate and auto-trading gate** are correctly implemented and
  correctly checked in the execution path — their problem is access control (1.1), not logic.

---

## 5. Priority

Only one item here outranks everything in the other two documents:

1. **1.1 — public unauthenticated API.** This should be closed before the live trading gate is
   ever switched on, and arguably before the next deploy regardless. Everything else in all three
   documents concerns a system that loses money slowly through bad logic; this one concerns a
   system that can be driven by someone else.
2. **3.1 and 3.2** — calibration overwrite and the missing sample-size floor. Both are small
   fixes, and both sit on the path to an unsupervised real order.
3. **2.1 and 2.2** — cost model and fill timing. These don't break anything, but until they're in
   place no backtest number should be used to decide whether a strategy is worth promoting, which
   is the entire purpose of the backtest engine.
