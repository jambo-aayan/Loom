# 17. API authentication: a shared secret, held server-side

## Status

Accepted

## Context

The FastAPI service had no authentication of any kind — no dependency, no middleware, no key
check — and was deployed with `--allow-unauthenticated` (`infra/gcp/setup.sh`) and
`CORSMiddleware(allow_origins=["*"])`. Anyone who found the Cloud Run URL could reach every
endpoint, and because no credentials were involved, a plain `fetch()` from any web page in any
browser worked too.

The reachable chain was complete: `POST /settings/live-trading-gate/enable` → `PATCH
/strategies/{id}` with `{"live_enabled": true, "approval_mode": "auto"}` → `POST
/settings/kill-switch/resume` → `POST /trading-pass/run?environment=live`. Every safety control
in `CONTEXT.md` was individually switchable by an anonymous caller, and the controls themselves
were implemented correctly — they simply had no access control in front of them.

ADR-0004 was the nearest existing decision, but it does not cover this. It reasons entirely about
**multi-tenancy** — user accounts, per-user isolation, billing — and concludes there is no need
for them with one user. That conclusion is sound and unchanged. It does not follow that a
money-moving API needs no access control on a public URL, and ADR-0004 never asks the question.
**Single-user is not single-visitor.**

Four options were considered:

1. **Cloud Run IAM / IAP** — strongest, but the dashboard is a browser client on Vercel, which
   has no Google identity to present without an OAuth flow or service-account plumbing.
2. **API key in the browser** (`NEXT_PUBLIC_…`) — not authentication at all; the key ships in the
   bundle for anyone to read.
3. **Session cookie with a single password** — works with direct browser→API calls, but those are
   cross-site (Vercel origin → Cloud Run origin), and cross-site cookies are increasingly blocked
   by default in Safari and Firefox. Fragile in a way that would fail silently and later.
4. **Shared secret, held server-side, with the frontend proxying through its own origin.**

## Decision

Option 4.

- Every request requires `X-Loom-Api-Key` matching the `LOOM_API_KEY` env var, enforced by
  middleware (`loom/api/auth.py`) in front of routing, compared with `secrets.compare_digest` so
  the key can't be recovered by timing the responses.
- **It fails closed.** An unset `LOOM_API_KEY` returns 503 to every protected request rather than
  serving them unauthenticated. A deployment that silently accepts anonymous money-moving
  requests is exactly the failure this ADR exists to prevent, so "no key configured" must never
  be the permissive case.
- **Two exemptions**, both deliberate:
  - `/health`, because Cloud Run's liveness probe cannot carry a secret.
  - `/action-links/*`, the emailed one-tap approve/reject path (story 64, ADR-0012), which is
    opened from a mail client with no login. It is exempt from the API key but *not*
    unauthenticated: each link carries its own signed, single-use, short-expiry token, verified
    server-side, and still routes through the full risk/sizing re-check (story 65).
- **The frontend proxies through its own origin.** `app/api/loom/[...path]/route.ts` is a Next.js
  route handler that runs server-side, attaches the key, and forwards to the backend. `API_BASE`
  in the browser is now the same-origin path `/api/loom`, so the key never enters a bundle and
  every call is same-origin. The service worker's notification approve/reject fetches go the same
  way, since a service worker cannot hold a secret either.
- `LOOM_API_KEY` and `LOOM_API_BASE_URL` are **server-side env vars**. Neither carries a
  `NEXT_PUBLIC_` prefix; adding one would publish them and undo the decision.
- CORS narrows from `*` to `frontend_base_url`. With the proxy in place no browser makes a
  cross-origin request here at all, so the allowlist exists to make a stray direct call fail
  visibly rather than silently work.

`--allow-unauthenticated` stays on the Cloud Run service: the Vercel proxy has no Google identity
to present, and application-level auth is now doing the work. Moving to IAP or Cloud Run IAM
later is a strict improvement and this decision doesn't block it.

## Consequences

- `LOOM_API_KEY` becomes a required secret. `infra/gcp/setup.sh` provisions `loom-api-key` and
  documents generating it; the same value must be set in Vercel. A deployment that skips it gets
  a loud 503 naming the variable, not a silent open door.
- Local development and CI need the variable set. The test suite's `conftest.py` sets it and
  gives `TestClient` a default header, so the 14 existing API test files were not touched.
- Every frontend API call gains one proxy hop. For a single-user dashboard this is not a
  meaningful cost, and it buys same-origin requests: no CORS, no cross-site cookie exposure, and
  no secret in the bundle.
- This is deliberately **not** multi-tenancy. There is still one user, no accounts, and no
  per-user isolation — ADR-0004 stands. A shared secret is the right size for one user and the
  wrong size for many; revisit it when there is a second user, not before.
- The emailed action-link path is now the only entry point reachable without the API key, which
  makes its signed-token verification load-bearing rather than belt-and-braces. It was already
  written that way (single-use, short-expiry, server-side verified), and its tests should be
  treated as security tests from here on.
