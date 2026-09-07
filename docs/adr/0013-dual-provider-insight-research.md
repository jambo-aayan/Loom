# 13. Dual-provider Insight research tier: free-auto vs paid-manual

## Status

Accepted

## Context

ADR-0009 scoped a two-tier `Insight` design but deliberately left the research tier's exact
provider/model unpicked ("pick at implementation time, not locked into this ADR") and only
shipped the screening tier in v1. Coming back to build the research tier (ticket #48, M5), we
worked through how it should actually fire and landed somewhere more specific than "a stronger
model" — the automatic and user-triggered paths should use genuinely different providers with
different cost profiles, not just different prompts against the same Anthropic account that
already powers screening and on-demand ask (#45).

## Decision

- **Research-tier eligibility is gated by `Strategy` style**, not just "already cleared a
  quantitative screen": only `investment`-style signals (today: Value/Quality Dip-Buyer) are
  ever eligible. `trading`-style strategies stay screening-only, permanently — this isn't
  "lean on it more" (ADR-0009's original, softer phrasing), it's a hard gate.
- **Two invocation modes, two providers:**
  - **Automatic / free**: runs unattended once an eligible signal reaches
    `pending_approval`/`auto_approved`, using Gemini Flash 2.5 (free tier) via a new
    `google-genai` dependency. This is the first non-Anthropic LLM boundary in the codebase —
    `InsightGenerator` gains a `GeminiInsightGenerator` implementation alongside
    `AnthropicInsightGenerator`, following the existing Fake-by-default pattern (a `FakeInsightGenerator` variant
    covers this path in tests, same as every other external boundary).
  - **Manual / paid**: user-triggered only, using Claude Sonnet 5. Never scheduled, never
    batched, never invoked as a side effect of anything else — the API endpoint has no automatic
    caller anywhere. The frontend requires an explicit confirm-with-cost-warning dialog before
    the request fires; there is no route to the paid tier that skips this.
- A new setting, `GOOGLE_API_KEY`, follows the same optional/blank-by-default pattern as every
  other credential (ADR-0004) — unset means the automatic research pass silently doesn't run
  (or falls back to the fake generator in dev/test), not an error.

## Consequences

- The codebase now depends on two LLM SDKs (`anthropic`, `google-genai`) instead of one. Swapping
  either provider later touches only its `InsightGenerator` implementation, not the interface or
  call sites — the existing Fake-by-default seam already isolates this.
- `Strategy.style` moves from descriptive metadata (ADR-0009: "read by the research tier... not
  a behavioral gate enforced elsewhere") to an actual behavioral gate for this one thing. Nothing
  else in the system currently branches on `style`.
- Manual/paid invocation being structurally unreachable except through an explicit, confirmed
  user action means there's no config flag or environment variable that could accidentally turn
  it into an automatic path later — that would require a new code path, not a settings change.
