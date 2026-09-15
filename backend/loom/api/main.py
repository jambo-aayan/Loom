import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from loom import db, logging_config, strategies  # noqa: F401  (strategies import registers the strategy registry)
from loom.api.auth import require_api_key
from loom.api.routers import action_links, backtests, insights, performance, portfolio, push, settings, signals, trading
from loom.api.routers import strategies as strategies_router
from loom.seed import seed_all_strategies
from loom.settings import get_settings

logging_config.configure()
logger = logging.getLogger("loom.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    session = next(db.get_session())
    try:
        seed_all_strategies(session)
    finally:
        session.close()
    yield


app = FastAPI(title="Loom API", version="0.1.0", lifespan=lifespan)

# Order matters: Starlette builds the stack outermost-last, so CORSMiddleware is registered
# *after* the auth middleware in order to wrap it — otherwise a 401/503 from auth would come back
# without CORS headers and the browser would report it as a network failure rather than the real
# status (the same trap the unhandled-exception handler below documents).
app.middleware("http")(require_api_key)

# The frontend calls this API through its own same-origin Next.js route handler (ADR-0017), so no
# browser ever makes a cross-origin request here. The allowlist is kept narrow rather than "*" so
# that a stray direct call from a page origin fails visibly instead of silently working.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_base_url],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Without this, an unhandled exception returns Starlette's bare default 500 with no body and
    no CORS headers, which the browser reports as a CORS violation — "Failed to fetch" in the
    frontend, indistinguishable from an actual network problem. Confirmed live: a genuine backend
    exception (an LLM-provider call using an invalid model id) surfaced exactly this way, with the
    real error invisible without digging through Cloud Run logs.

    Registering a handler for the base `Exception` doesn't fully fix this on its own: Starlette
    special-cases it onto `ServerErrorMiddleware`, which sits *outside* `CORSMiddleware` in the
    stack (`ServerErrorMiddleware -> CORSMiddleware -> ExceptionMiddleware -> router`) — so a
    response built here still never passes back through CORSMiddleware to pick up its headers.
    The CORS header is added by hand below instead of relying on the middleware for this one path
    (mirrors the permissive `allow_origins=["*"]`/no-credentials config above exactly)."""
    logger.exception("unhandled exception in %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error"},
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(strategies_router.router)
app.include_router(signals.router)
app.include_router(portfolio.router)
app.include_router(settings.router)
app.include_router(backtests.router)
app.include_router(trading.router)
app.include_router(performance.router)
app.include_router(push.router)
app.include_router(action_links.router)
app.include_router(insights.router)
