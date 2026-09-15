# Spec vs. Implementation Audit

What the planning documents promise versus what the code actually does. Sources audited:

- `CONTEXT.md` (domain glossary)
- GitHub issue #1 (the v1 spec — 78 user stories, 41 sub-issues)
- `docs/adr/0001`-`0016`
- `BACKLOG.md`

Companion to `docs/strategy-and-universe-gap-analysis.md`, which covers code-level defects in
the strategies and universe. This document covers **conformance**: where the build and the plan
disagree.

Findings are ordered by how misleading they are, not by effort to fix. The first section is the
dangerous one — places where a document or docstring asserts something that isn't true, so
nobody would think to look.

---

## 1. Documented as done, but not true

### 1.1 `owner_id` exists on 1 of 14 tables

`loom/models.py:4` states:

> Every row carries a nullable `owner_id` scaffolding column for future multi-tenancy (story 73)

Story 73 asks for it on "every persisted record ... so that multi-tenancy could be added later
without a schema rewrite." ADR-0004 rests on the same promise.

Actual coverage:

| Has `owner_id` | Missing it |
|---|---|
| `Strategy` | `StrategyConfigVersion`, `Book`, `Signal`, `Order`, `KillSwitchEvent`, `LiveTradingGateEvent`, `AutoTradingGateEvent`, `Insight`, `BacktestRun`, `ConfidenceCalibration`, `PushSubscription`, `SignedActionLink`, `DailyAccountSnapshot` |

One of fourteen. The seam the story exists to provide does not exist, and the file comment says
it does — so adding multi-tenancy later still means the schema rewrite story 73 was written to
prevent.

### 1.2 Counterfactual simulation does not use the strategy's exit rules

`loom/backtest/counterfactual.py:1` states it reuses "the originating strategy's exit rules."
CONTEXT.md and ADR-0011 both say the same — "applying the originating `Strategy`'s own exit
logic against real subsequent market data."

`simulate_counterfactual(...)` takes an `ExitPlan` and nothing else. No `Strategy` is passed in,
`generate_signals` is never called, and exits are decided purely by `check_exit` (target / stop /
time).

For Compounder, Harvester and Dip-Buyer this is roughly equivalent, because their exit plans
mirror their exit logic. For the other two it is not:

- **Trend Follower** really exits on a death cross. Its counterfactual exits on an 8% stop or a
  180-day timer — a policy the strategy does not have.
- **Volatility Breakout** really exits on volatility normalisation (measured average hold: 6.6
  days). Its counterfactual exits on a 6% stop or a 45-day timer.

`DEFAULT_MAX_HORIZON_DAYS = 90` compounds it: Trend Follower's own `time_exit_days` is 180, so
its counterfactuals can only ever resolve via the stop or come back `still-open`.

This matters more than it looks. The counterfactual is the mechanism behind the project's
headline idea — "is my own approve/reject judgment adding value" (stories 67/69, ADR-0011). For
two of five strategies it currently scores the user against a policy that never existed.

### 1.3 The `Manual` Book cannot see anything it was built for

ADR-0010 and story 36:

> any position I hold that wasn't opened by a strategy — including my existing sector Pies (data
> companies, semiconductors, ETFs) ... automatically classified as `Manual` via reconciliation

`loom/reconciliation.py:manual_positions` implements this correctly. But it calls
`broker.get_positions()`, which maps every T212 ticker through `from_t212(...)` with no error
handling (`loom/execution/t212_client.py:168`), and `from_t212` raises `UnmappedInstrumentError`
on anything outside the 4-entry static map.

So reconciliation can only ever see the four instruments the strategies already trade — and
throws outright if the account holds anything else. The pre-existing sector Pies that motivated
the feature are exactly the case that breaks it.

### 1.4 Account-level risk limits are enforced per-Book

ADR-0010 and story 39 are explicit:

> Kill switch and account-level exposure/risk limits are computed across the whole `Environment`
> (every `Book` plus `Manual`)

The kill switch does this correctly (scoped by `Environment`). The **risk limits do not**:
`size_and_check` receives the per-book `AccountState` from `account_state_for_book(...)`, so
`max_position_size_pct` (15%) and `max_total_exposure_pct` (90%) are applied per strategy. Five
strategies can each put 15% of account value into the same instrument with every check passing.

ADR-0010 even anticipates the inverse layer — "a per-`Book` capital allocation limit ... is an
additional layer on top, not a substitute" — and what exists is only the per-Book behaviour,
without the account-level check it was meant to sit on top of.

### 1.5 ADR-0009 assigns Compounder to `investment`; the code says `trading`

ADR-0009: "`investment` (Compounder, Value/Quality Dip-Buyer)". Both
`LowVolCompounder.style` and the seeded `StrategyModel.style` (`loom/seed.py:17`) say `trading`.

`loom/insight/research.py:23` gates the research tier on the DB column, so Compounder is denied
the research tier ADR-0009 assigns it. (Also noted in the companion document.)

---

## 2. Specced, never built

### 2.1 Story 13 — CORRECTED: the scheduled pass exists

An earlier revision of this document claimed story 13 was never built. That was wrong.
`infra/gcp/setup.sh` provisions four Cloud Scheduler jobs triggering Cloud Run Jobs (ADR-0002's
"scheduled single-pass, not a daemon"):

| Job | Schedule |
|---|---|
| `loom-trade-pass` | `0 8 * * 1-5` — weekdays 08:00 UTC |
| `loom-screen-insights` | `15 8 * * 1-5` |
| `loom-research-insights` | `30 8 * * 1-5` |
| `loom-reconcile` | `0 18 * * 1-5` |

Story 13 is implemented and conformant. All jobs are pinned to `--environment demo`; there is no
scheduled live pass, which is correct while the live trading gate is off.

Worth verifying operationally that `setup.sh` was actually applied to the project rather than
existing only as a script — `gcloud scheduler jobs list` answers it.

### 2.2 Story 3 — there is no Demo/Live switch in the dashboard

> As the user, I want a persistent switch in the dashboard between Demo and Live views, so that
> I can inspect or test either at any time without restarting or reconfiguring anything.

ADR-0007 and CONTEXT.md both describe the two environments as permanently side by side, "comparable
to an exchange's testnet/live toggle."

The frontend hardcodes `"demo"` in 25 places across 9 files (`app/page.tsx`, `approvals`,
`history`, `performance`, `settings`, `insights`, `strategies/[id]`, `lib/api.ts`,
`components/RegisterServiceWorker.tsx`). There is no environment selector component and no
environment state anywhere in the UI.

`toggleLiveTradingGate` in Settings is a different concept — the global **Live trading gate** from
CONTEXT.md, not an environment switch. Turning it on would not make the live environment
reachable, because nothing in the UI can address it.

### 2.3 Stories 24 and 25 — risk limits are neither configurable nor per-strategy

> 24. ...configurable limits (max position size, max total exposure, a daily loss limit...)
> 25. ...risk limits to apply both globally and per-strategy, so that I can constrain an unproven
>     strategy more tightly than one I trust.

`RiskLimits` is a frozen dataclass with hardcoded defaults, and every call site constructs it as
`limits or RiskLimits()` — `backtest/engine.py:142`, `daily_loss.py:59`, `trading_pass.py:323`.
There is no DB table, no settings endpoint, and no UI. The Settings router exposes only the kill
switch and the two gates.

Ticket #29 ("Settings — risk limits + kill switch, wired live") is open, so the gap is known —
but story 25's per-strategy dimension has no implementation path at all: nothing in the schema
can express a per-strategy limit.

### 2.4 Story 77 — comparing two saved backtest runs

Partially built. The spec's Solution section says:

> Saved backtest runs can be compared against each other, surfacing the literal parameter
> differences between the two config versions being compared

What exists (`POST /strategies/{id}/draft-backtest`) compares **a draft against the current
promoted version**, with a real `param_diff`, surfaced in the strategy detail page. That covers
story 78 fully and story 77's *intent*.

What doesn't exist is run-vs-run comparison: there is no compare endpoint over saved
`BacktestRun` rows, and the Backtest page only carries a line of text pointing users to the
strategy page. Also worth noting the draft backtest is never persisted as a `BacktestRun`, so a
draft result is discarded on navigation despite story 47's "saved and named rather than
discarded."

---

## 3. Deliberate deviations that are correct but under-documented

### 3.1 The kill switch is database-backed, not a flag file

Issue #1 specifies it twice: "a local flag file, checked before every order submission."

`loom/killswitch.py` uses the most recent `KillSwitchEvent` row instead, and the module docstring
gives a good reason — Cloud Run runs multiple stateless instances that share no filesystem, so a
file reflects one container's local disk. This is the right call.

But it is recorded only in a module docstring. There is no ADR, and issue #1 still says "flag
file" in both the Solution section and the Implementation Decisions. Per `docs/agents/domain.md`,
an implementation that contradicts a decision should surface it rather than silently diverge.
This one diverged silently and correctly.

### 3.2 Insight provider is Gemini-first, not Claude

Issue #1 says "An LLM-powered Insight layer (Claude, using its web-search tool)". Reality is
Anthropic-when-configured with Gemini fallback, and in practice Gemini. **This one is properly
documented** — ADR-0016 records it explicitly, including why (no Anthropic key was ever
provisioned while a Google one existed). Noted here only to contrast with 3.1.

---

## 4. Documents that are now stale

- **Issue #1 still describes the kill switch as a flag file** (3.1) and Insights as Claude-based
  (superseded by ADR-0016).
- **Ticket status no longer reflects the code.** Tickets #32-#38 are open, but all five
  strategies, `calibration.py`, `correlation.py` and `evaluation.py` are implemented. Issue #1
  reports 21/41 sub-issues complete; the true figure is higher, which makes the tracker useless
  for judging what's left.
- **Tickets #23-#26 duplicate the closed #19-#22** (same titles, "M1·V1..V4" vs "V1..V4"), so the
  completion percentage is wrong in both directions.
- **`BACKLOG.md` treats the 4-instrument universe as a safe assumption** in the signal-volume
  entry ("Fine while the universe is 4 instruments across 5 strategies"). The companion document
  shows the universe is itself the binding constraint, not a benign simplification.
- **`CONTEXT.md`'s only open question is the universe.** Its "Open / not yet resolved" section
  reads: *"Vocabulary for the strategy's target universe ... not yet formalized as a term."* That
  unresolved item turned out to be the thing blocking the system, which is a good argument for
  closing it next.

---

## 5. What is actually built and matches the spec

Worth recording so the audit isn't read as uniformly negative. Verified present and conformant:

- **Idempotent order submission** with rate-limit pacing off `x-ratelimit-*` headers and full
  request/response logging (stories 8, 9, 10; ADR-0006, ADR-0014).
- **Signal lifecycle, approval pipeline, notes, permanent retention** (stories 26-30, 66, 68).
- **Both global gates** — Live trading gate and Auto-trading gate — exactly as CONTEXT.md
  describes them, including the non-destructive circuit-breaker semantics.
- **Strategy config versioning with draft → promote**, and draft backtesting with a real
  parameter diff (stories 23, 78).
- **Evaluation metrics in full**: max drawdown, win rate, profit factor, expectancy, Sharpe,
  Sortino, rolling Sharpe (story 70), plus cross-book correlation (story 70) and
  instrument/sector drill-down (story 72).
- **Insight screening tier, digest, and chart-annotated trigger** — story 55 is implemented
  (`SignalChartView` draws the trigger line and marker), which ticket #42's open state
  understates.
- **Mobile navigation exactly as ADR-0012 specifies**: five-item bottom tab bar
  (Overview/Approvals/Strategies/Backtest/Insights) plus History and Settings as header icons.
- **Push subscriptions, signed action links, per-strategy notify threshold** (stories 62-64).
- **Backtest engine** with fake clock, no lookahead, simulated fills, benchmark comparison, and
  shared risk/sizing with live (stories 42-46).

---

## 6. Suggested handling

Grouping by what kind of work each needs:

**Correct the documents** (no code): issue #1's flag-file and Claude references; the
`models.py` and `counterfactual.py` docstrings that assert things that aren't true; ticket
status and the duplicate #23-#26.

**Small, well-defined code fixes**: Compounder's `style` (1.5); `owner_id` columns on the
remaining 13 tables (1.1) — one migration, and cheaper now than after more rows exist.

**Needs a design decision first**:
- Counterfactual fidelity (1.2) — either pass the strategy in and call its real exit logic, or
  narrow what the docs claim. This interacts with the live exit-enforcement work in the
  companion document; both are really the same question of where exit logic lives.
- Account-level vs per-Book risk (1.4) and per-strategy limits (2.3) — one schema change and
  one clear rule about which layer checks what.
- Unmapped-ticker handling (1.3) — degrade to an untracked Manual holding, or resolve tickers
  dynamically against T212's instrument metadata.

**Straightforward but not small**: the Demo/Live switch (2.2) — not hard, but load-bearing for
the product as described.
