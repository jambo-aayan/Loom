# Backlog

Ideas and decisions deliberately deferred past v1, captured here so they aren't lost. Nothing here is scoped or committed — just worth coming back to.

## Product features

- **No-code parameter tuning for backtests.** Adjusting a strategy's parameters (RSI thresholds, profit targets, etc.) currently means editing config/code and re-running a backtest. A UI for tweaking parameters and re-running without touching code would make iteration faster, but is real scope on its own — worth doing once the basic backtest loop is proven, not before.
- **Reinforcement learning / auto-tuning strategies.** The idea of a strategy that adjusts its own logic from performance feedback. Deliberately not pursued for v1 — non-stationary markets, sample inefficiency, and overfitting risk make this a bad early bet, and it clashes with the "manual approval until proven" caution baked into the rest of the design. Revisit only once there's enough real trading/backtest history to make it a genuine option rather than a shiny distraction.
- **Auto-promotion from paper to live.** A strategy's `live-enabled` flag is manually set by the user after reviewing its track record. Automatic promotion based on hitting some performance bar is a natural extension, but ties into the RL question above and shouldn't happen without deliberate design.
- **Strategies beyond the v1 roster of five.** v1 ships five strategies (see `docs/adr/0009-v1-strategy-roster.md`), not just one — the `Strategy` interface is designed to support many more; building a sixth is future ticket work, not blocked on anything architectural.
- **`Insight` research tier.** v1 ships the cheap screening tier only (news/sentiment summary, free-tier model). The deeper multi-source research tier (runs only on candidates that clear a strategy's quantitative screen, so stays low-volume even on a pricier model) is a near-term fast-follow once the screening tier and the rest of the pipeline are proven — see `docs/adr/0009-v1-strategy-roster.md`.
- **Mirroring `Book`s as real Trading 212 Pies.** ADR 0010 chose a software-level `Book` ledger over Trading 212's Pies API for core portfolio attribution (a Pies endpoint is currently marked deprecated in T212's docs, and order-to-pie routing isn't documented). Once/if that API stabilizes, mirroring each `Book` as a real Pie so it's also visible natively in the T212 app is a plausible visualization-layer nice-to-have — not the backbone, not built for v1.
- **LLM-driven `Strategy`.** Right now `Insight` (LLM commentary/research) is explicitly advisory-only and can never itself trigger a trade. A future `Strategy` implementation that uses LLM reasoning to actually generate `Signal`s is a natural next step once the advisory-only version has proven useful — it would still flow through the same risk/sizing and approval gates as every other strategy, no special-casing.
- **Multi-tenancy / real product.** v1 is single-user (just the founder's account), with cheap seams left in (nullable `owner_id`-style columns) so multi-tenancy could be added later without a rewrite. Actual auth, per-user data isolation, and billing are all deliberately not built yet.
- **Richer notification channels.** v1 assumes email for "signal pending approval / kill-switch triggered / order failed" alerts, as the simplest thing that works. Push notifications or Telegram could be nicer but add integration work not needed to prove the concept.
- **Fallback/secondary market-data provider.** Twelve Data is the v1 choice (free tier: 800 calls/day, LSE + US coverage, official Python client). Financial Modeling Prep is the noted fallback if richer fundamentals are needed or the free tier is outgrown; yfinance is the backtesting/backfill supplement, not a production dependency.
- **Frontend E2E tests (Playwright).** v1's frontend testing is the OpenAPI contract between Next.js and FastAPI. Full browser E2E tests against a seeded database are worth adding once the UI stabilizes, not while it's still moving fast.

## Technical / architecture

- **Community Trading 212 SDKs** (`python-trading212`, `t212-api`) were audited and rejected for v1 — both are single-maintainer, low-adoption projects unsuitable for a Live money-moving dependency. We're writing our own thin client, borrowing `t212-api`'s rate-limit/pagination patterns as reference. Worth re-checking if either project gains real adoption later.
- **Deployment target** not yet decided. Vercel is a plausible fit for the Next.js frontend given it's already available as a connected tool in this environment, but this hasn't been discussed or decided — raise it explicitly when we get to deployment, don't assume it.

## Process notes

- On model choice: default to Sonnet for well-scoped implementation tickets; use Opus for spec/architecture work and anything touching the risk/sizing or execution/idempotency layers, where a subtle bug is costly. No strong recommendation yet on where (if anywhere) Fable fits this project specifically — worth experimenting with on low-stakes tasks (UI copy, wording) if curious, not built into any workflow rule.

## Open loops

- Aayan mentioned mid-conversation that he'd had "one more thing to say" about the project and forgot what it was. Flagged here in case it resurfaces — worth asking him again before the spec is finalized, in case it changes anything.
