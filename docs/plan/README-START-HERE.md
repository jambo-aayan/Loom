# Loom rebuild plan: start here

This folder is the output of a long planning session (22–23 Sep 2026) covering Loom's strategies, safety, sizing, data, features, UI and launch plan. It was written against a snapshot of the repo (`Loom-main`, Sep 2026) and backed by research run on real market data.

**It supersedes older planning material wherever the two disagree.** Where it conflicts with the code, the code is the current state and this folder is the target.

## Where to put this

- Copy this folder into the repo as `docs/plan/`.
- Copy the UI design file `Loom_Minimal_v4__standalone_.html` into the repo as `docs/design/loom-v4.html`. It is the visual reference for all UI work.
- `CONTEXT.md` (glossary) and `docs/adr/` remain the domain docs. As each decision in `02-decisions.md` is implemented, write the matching ADR (see "ADRs to write" in that file) and update `CONTEXT.md`.
- Tasks in `07-build-plan.md` are meant to become GitHub issues (see `docs/agents/issue-tracker.md`).

## Reading order

| File | Read when |
|---|---|
| `01-current-state.md` | First. What exists, what's broken, what's missing, verified against code |
| `02-decisions.md` | Before any change. Every decision and why |
| `03-strategy-specs.md` | Before touching any strategy. Exact formulas and parameters |
| `04-sizing-and-risk.md` | Before touching risk, sizing, the budget fence, pause/halt |
| `05-data-and-execution.md` | Before touching market data, scheduling, orders, exits |
| `06-ui-spec.md` | Before touching the frontend |
| `07-build-plan.md` | To pick the next task. Ordered, with acceptance criteria |
| `08-research-log.md` | When tempted to change a rule. Every test run and its result |
| `09-phase0-findings.md` | Phase 0 T0.1/T0.2 findings (22 Sep 2026) behind decisions D25, D31–D33 |
| `LAUNCH-TIMELINE.md` | For Aayan. Phases, gates, go-live and budget rules |

## What Loom is (one paragraph)

A single-user web app that trades a Trading 212 Stocks ISA automatically. Four rule-based strategies propose trades; the user approves them (or a strategy auto-approves once proven); an **exit enforcer** sells positions when they hit a stored target price, stop price or time limit. Loom manages only its own budget (£1,000 to start) inside a larger ISA and never touches the user's other holdings. Everything runs in the T212 **Demo** environment first; a strategy is promoted to **Live** only when its demo track record matches the research.

## Working rules for Claude Code

1. **Demo only.** Never enable the live-trading gate, never point a job at the live environment, never place a live order. Aayan does that by hand.
2. **Safety before features.** Phase 0 of `07-build-plan.md` comes first. Do not start strategy or UI work while exit enforcement, sizing or the budget fence are incomplete.
3. **Strategy rules are specified exactly. Do not "improve" them.** Every threshold in `03-strategy-specs.md` came from a measured test (`08-research-log.md`). If a rule looks wrong, flag it; do not change it.
4. **AI output is advisory only.** Nothing from the insight/LLM layer may feed confidence, sizing, ranking or approval.
5. **Every safety invariant gets a test.** The list is in `04-sizing-and-risk.md` ("Invariants"). A change that breaks one is a bug even if a feature works.
6. **Flag conflicts, don't guess.** If the code contradicts these docs in a way that changes behaviour, stop and report it with file references.
7. **Keep the glossary current.** New terms introduced here (Loom budget, sleeve, slot, instrument group, exit enforcer, shadow, pause, halt) go into `CONTEXT.md`.
8. **Units and currency are explicit everywhere.** Prices are normalised to GBP at the data boundary; instrument currency is read from metadata, never inferred from the exchange.

## New glossary terms (add to CONTEXT.md)

- **Loom budget**: the fixed amount of money Loom may use. All sizing is computed from the Loom budget's current value (Loom's cash + Loom's positions), never the ISA total.
- **Sleeve**: a strategy's share of the Loom budget (%).
- **Slot**: one concurrent position a strategy may hold. Per-trade size = sleeve ÷ slots.
- **Instrument group**: instruments that track essentially the same thing (daily-return correlation ≥ 0.95). Caps apply per group.
- **Exit levels**: `target_price`, `stop_price`, `exit_by` stored on every Loom position at entry.
- **Exit enforcer**: the scheduled job that compares live T212 prices with exit levels and sells.
- **Shadow**: a strategy or config that generates and tracks signals but never places orders.
- **Pause (new trades)**: entries blocked; exits keep running.
- **Halt (everything)**: every order blocked, sells included. Manual, emergency only.
- **Market regime**: whether the broad-market index is above its 200-day average (uptrend) or below it.

## Suggested skills

Available as user skills in Aayan's setup:
- `grill-with-docs`: sharpen a design and write ADRs/glossary entries as you go. Use when a task in the build plan needs more design.
- `to-spec`: turn a build-plan phase into GitHub issues.
- `prototype`: throwaway prototypes for state-model questions (e.g. capital lending).
- `handoff`: end-of-session handoff for the next agent.
- `frontend-design`: for the UI rebuild, alongside `docs/design/loom-v4.html`.
