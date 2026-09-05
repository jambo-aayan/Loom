# Handover: UI/design pass + spec-to-tickets session

Context for whoever (or whichever Claude session) picks this up next. Everything in this file is
session narrative — decisions, artifacts, and reasoning that exist because of one long working
session, not things you'd naturally reconstruct just by reading the committed docs. The committed
docs (`CONTEXT.md`, `docs/adr/`, GitHub issue #1) are still the source of truth for the domain
model and spec; this file is the map to *how they got that way* and where the non-repo artifacts
live.

## 1. What this session actually did, in order

1. Renamed the local clone from `trader_bot_t212` to `loom` (cosmetic only — the GitHub repo
   itself was already renamed `jambo-aayan/Loom`; `jambo-aayan/trader_bot_t212` still resolves via
   GitHub's redirect, and the repo's own docs still say `trader_bot_t212` in a couple of places —
   don't "fix" that, it's just an old name that still works).
2. Built a full UI design pass: a 20-artboard mockup canvas (desktop + mobile, every major page)
   using the `/design` skill, then a *separate*, fully-interactive click-through prototype with
   fake data and real client-side state, built as a hand-written HTML/CSS/JS Artifact (not part of
   the canvas — canvas artboards can't share state/navigation with each other, so a "click through
   it for real" prototype had to be a different kind of artifact entirely).
3. Ran `/mattpocock-skills:to-spec` to check the existing spec (issue #1) for gaps the UI work
   surfaced, resolved them with the user, and folded the results into `CONTEXT.md`, ADR-0012, and
   `BACKLOG.md` (already committed — see §4).
4. Ran `/mattpocock-skills:to-tickets` twice — the first pass produced 17 issues that were
   **horizontal layer slices** (schema ticket, client ticket, etc.), which is exactly what the
   skill's vertical-slice rule prohibits (a ticket should be demoable end-to-end on its own). Those
   17 were closed as `not_planned` and redone properly. **If you see closed issues `#2`–`#22`,
   that's why — they're not bugs or abandoned work, just a wrong first cut, explicitly superseded.**
5. Published 20 proper vertical-slice tickets across three milestones, all as sub-issues of `#1`:
   `#23`–`#31` (M1, tracer bullet), `#32`–`#38` (M2, roster + evaluation depth), `#39`–`#42` (M3,
   mobile notification infra). Full breakdown in §5.

## 2. The UI artifacts — where they actually live

**Neither of these is discoverable from the repo alone without this file.** Both now have a
durable copy committed here under `design/`, plus a live hosted version.

### 2a. Design canvas — 20-artboard mockup

- **Live artifact** (viewable, click-to-select editable if canvas saving is enabled for the
  account): https://claude.ai/code/artifact/1c516149-98af-447d-b105-7bea735ac770 — titled "Loom
  Dashboard".
- **Source committed here**: `design/canvas/*.dc.html` (20 artboards) + `design/canvas/canvas.json`
  (layout manifest — positions, sizes, sticky-note annotations documenting what each phase added).
- **What it covers**: desktop *and* mobile versions of Landing, Onboarding, Overview, Approvals,
  Strategies, Strategy detail, Backtest, Backtest Compare, Insights, History, Settings, Performance
  Compare, and Instrument drill-in. Every board has a light/dark theme prop.
- **To re-seed/re-publish this canvas from the source files**: use the `/design` skill's
  `seed-canvas.mjs` tooling (bundled with the skill, not in this repo) against `design/canvas/`.
  The skill's own docs cover this — don't hand-roll it.
- **Landing/Onboarding boards are intentionally NOT part of v1 scope** — see §4. They're kept here
  as a primary source for whenever multi-tenancy is tackled, not because they were missed.

### 2b. Interactive prototype — fully click-through, fake data

- **Live artifact**: https://claude.ai/code/artifact/47259815-cc1f-430e-9fc8-f82130b48092 — titled
  "Loom Prototype". Works on phone and desktop (responsive, not two fixed mockup widths).
- **Source committed here**: `design/prototype/loom-prototype.html` — single self-contained file,
  vanilla JS, no build step, no framework. Open it directly in a browser to see/edit it.
- **What actually works in it** (not just visual — real client-side state):
  - Real navigation between Overview / Approvals / Strategies (+ detail) / Backtest / Insights /
    History / Settings.
  - Approve/Reject mutates state for real: removes the signal from the pending queue, updates nav
    badge counts, writes a row into History with either a real outcome or (on reject) a randomly
    generated counterfactual outcome — mirroring the domain concept `Counterfactual outcome` from
    `CONTEXT.md`.
  - Per-strategy auto-approve threshold and notify-threshold sliders are real `<input type=range>`
    elements that write back into strategy state live.
  - Kill switch is global: flips a banner, disables all Approve buttons app-wide.
  - Demo/Live switch changes the displayed portfolio balance *and* the Positions list (each
    environment has its own small fake position set) — this was a deliberate fix after the first
    version only changed the balance number, which undercut the point of the switch.
  - Strategy detail page has a full trade log table + a live cumulative-return SVG chart + a
    per-trade return bar chart, computed from a per-strategy fake trade dataset
    (`TRADES` object near the top of the `<script>` block) — added after the user specifically
    asked for "all their trades, returns per trade, plots, performance metrics," not just
    aggregate stats.
  - Light/dark theme toggle persists via `localStorage`.
  - Backtest picker fakes swapping between a few canned result sets by config version, giving the
    illusion of a responsive backtest without a real engine.
- **What does NOT persist**: everything except the theme resets on page refresh (all other state
  lives in plain JS variables, no backend). This is expected/fine for a fake-data click-through —
  don't try to "fix" it by wiring up localStorage for everything; real persistence belongs in the
  actual build (M1, not this prototype).
- **Design tokens used throughout both artifacts** (reuse these verbatim in the real frontend
  build — M1·V4, `#26` — rather than reinventing them):
  - Colors: dark ground `#0B0C0F`, light ground `#F3F2EF`, indigo accent `#6C7BFA`
    (dark-mode `#8B97FC`), mint/positive `#7FF5CC`, pink/negative `#FF8FCB`, amber/pending
    `#A86F0C` (dark `#F5B942`), danger/kill-switch-only `#F2555A`.
  - Fonts: Tiro Bangla (wordmark only), Space Grotesk (headings), IBM Plex Sans (body), IBM Plex
    Mono (all numbers/figures) — loaded via Google Fonts.
  - Mobile nav: 5-item bottom tab bar (Overview/Approvals/Strategies/Backtest/Insights) + 2 small
    header icon buttons for History/Settings on every screen. This exact pattern is now the
    documented decision in ADR-0012 (see §4) — it isn't just prototype styling, it's a resolved
    spec decision.
  - Logo: 4 converging curved SVG paths at increasing opacity ending in a solid dot.

## 3. Two review/QA passes worth knowing about

- The mobile-parity pass was reviewed by a background agent, which caught a real inconsistency
  (notify-bell icon missing from 2 of 3 mobile Approvals cards) and two near-overflow layout risks
  (Backtest and MobileHistory boards were within ~20-30px of their frame's bottom edge) — both
  fixed by tightening padding, not growing the frames (growing a frame cascades into
  `canvas.json`'s row-spacing convention for every board below it).
- The interactive prototype had a real bug caught by the user, not by review: a leftover
  half-finished sentence shipped as real UI copy in the Compounder's version-history note
  ("Tightened loss limit −2.5% → −2.0%… wait −2.5% is current."). Fixed. Worth a reminder to read
  your own generated copy once before publishing, not just the code.

## 4. Spec/domain doc changes from this session (already committed, commit `71e316e`)

The UI work surfaced 5 real gaps against the existing spec. Four were folded in, one was
deliberately kept out:

1. **Strategy detail needs a trade log + live equity curve**, not just params/changelog — added as
   stories 75/76 in issue `#1`.
2. **Mobile nav pattern was an open question in ADR-0012** ("sixth tab or different pattern") —
   now resolved in the ADR itself: 5-tab bar + 2 header icons (see §2a design tokens above).
3. **Backtest Compare should show literal parameter diffs**, not just prose — story 77.
4. **`Strategy config version` gained a `draft` status** — backtestable before being promoted to
   an official numbered version. Added to `CONTEXT.md`'s glossary and issue `#1` as story 78.
5. **Onboarding/account-connection UI is explicitly OUT of v1 scope** — the Landing/Onboarding
   mockups imply a UI for entering your own Trading 212 API key, but that contradicts ADR-0004
   (secrets are env-config, developer-set, single-user, never DB-stored). This was a deliberate
   call, not an oversight — don't build it as part of M1/M2/M3. Parked in `BACKLOG.md` under the
   existing multi-tenancy entry.

## 5. Current ticket state — start here

GitHub issue `#1` is the spec (updated, see §4). All build work is tracked as its sub-issues:

- **`#2`–`#22`**: closed, `not_planned`. Wrong first cut (horizontal slices). Ignore, don't reopen.
- **Milestone 1 (tracer bullet)** — `#23`–`#31`, in dependency order. **`#23` (repo scaffold) is
  the only ticket with no blockers — it's the actual starting point.**
- **Milestone 2 (roster + evaluation)** — `#32`–`#38`. `#32`–`#35` (the remaining four strategies)
  only block on M1's strategy-interface/backtest ticket (`#24`) and demo-pipeline ticket (`#25`),
  so they can be worked in parallel once M1 lands, not strictly after M1 finishes entirely.
- **Milestone 3 (mobile notifications)** — `#39`–`#42`.

Per the mattpocock-skills workflow already in use on this project: pick up with `/implement`
against `#23`, `/clear`ing context between tickets since each is self-contained by design.

## 6. Small things worth knowing that aren't written down anywhere else

- The working branch is `claude/plugin-marketplace-setup-r2b9vk` — an artifact of how this session
  was originally spun up, unrelated to its actual content. Don't read anything into the name.
- `BACKLOG.md` still has an open loop from Aayan: *"mentioned mid-conversation that he'd had 'one
  more thing to say' about the project and forgot what it was"* — worth asking him again before
  treating the spec as fully final.
- `BACKLOG.md`'s process notes: default to Sonnet for well-scoped tickets, Opus for spec/
  architecture work and anything touching risk/sizing or execution/idempotency (a subtle bug there
  is expensive) — worth following when picking a model for each M1/M2/M3 ticket.
- Deployment target is still explicitly undecided (`BACKLOG.md`) — Vercel is *available* in this
  environment but that's not the same as it having been chosen; raise it explicitly if/when it
  becomes relevant, per the existing note.
