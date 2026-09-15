"""API authentication (ADR-0017).

Every endpoint except the two exemptions below requires a shared secret in the
`X-Loom-Api-Key` header, matched against `LOOM_API_KEY`. Single-user v1 (ADR-0004) means there
are no user accounts to authenticate against — but single-user is not single-visitor, and the
Cloud Run service is deployed `--allow-unauthenticated`, so without this every safety control in
CONTEXT.md (kill switch, live trading gate, auto-trading gate, per-strategy `live-enabled`) was
switchable by anyone who found the URL.

**Fails closed.** An unset `LOOM_API_KEY` rejects every protected request with 503 rather than
serving them unauthenticated. A misconfigured deployment that silently accepts anonymous
money-moving requests is precisely the failure this module exists to prevent, so "no key
configured" must never be the permissive case.
"""

from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from loom.settings import get_settings

API_KEY_HEADER = "X-Loom-Api-Key"

# `/health` is Cloud Run's own liveness probe, which cannot carry a secret.
#
# `/action-links/*` is the emailed one-tap approve/reject path (story 64, ADR-0012). It is
# deliberately reachable without the API key because it is opened from an email client with no
# login — but it is not unauthenticated: each link carries its own signed, single-use,
# short-expiry token, verified server-side, and still routes through the same approval path with
# the full risk/sizing re-check (story 65).
EXEMPT_PREFIXES = ("/health", "/action-links")


def _is_exempt(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in EXEMPT_PREFIXES)


async def require_api_key(request: Request, call_next):
    if _is_exempt(request.url.path):
        return await call_next(request)

    configured = get_settings().loom_api_key
    if not configured:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "LOOM_API_KEY is not configured; the API refuses to serve requests without it. "
                    "See docs/adr/0017-api-authentication.md."
                )
            },
        )

    provided = request.headers.get(API_KEY_HEADER, "")
    # Constant-time comparison: a plain `==` short-circuits on the first differing byte, which
    # leaks the key a character at a time to anyone able to time the responses.
    if not secrets.compare_digest(provided, configured):
        return JSONResponse(status_code=401, content={"detail": "invalid or missing API key"})

    return await call_next(request)
