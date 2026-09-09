# 16. Screening tier and on-demand "ask" fall back to Gemini, not just Anthropic

## Status

Accepted — amends ADR-0013.

## Context

ADR-0013 deliberately kept the screening tier and on-demand "ask" (#45) on Anthropic only,
reserving Gemini for the automatic research tier alone — two providers with two different cost
profiles, on purpose. In practice, only a Google API key was ever actually provisioned for this
deployment; the Anthropic secret exists (`loom-anthropic-api-key`) but was never populated with a
real key. Confirmed live: with no Anthropic key, `get_insight_generator()` silently fell through
to `FakeInsightGenerator` for the screening tier, position commentary, and "ask" — the "ask"
feature appeared broken (canned template text, no real research), and the intended fix — wiring
up Gemini for it — turned out to already be available, just not reachable from this path.

## Decision

`get_insight_generator()` (`loom/api/deps.py`) now falls back to `GeminiInsightGenerator` when
`ANTHROPIC_API_KEY` isn't configured but `GOOGLE_API_KEY` is, before finally falling back to
`FakeInsightGenerator` when neither is set. This applies to the screening tier, position
commentary, and "ask" — every caller of `get_insight_generator()`. The automatic/paid research
tier split from ADR-0013 (`get_research_generator()` / `get_paid_research_generator()`) is
unchanged: those two functions still resolve to exactly the provider ADR-0013 chose for each,
with no fallback between them.

## Consequences

- Every LLM-backed feature in the app now runs on whichever real provider is actually
  configured, rather than requiring both keys to be populated (Anthropic first, matching v1's
  original assumption) before any of them use a real model.
- If Anthropic is later configured too, it silently takes over the screening/ask/position-
  commentary path again (Anthropic still preferred first) — no code change needed to switch back.
