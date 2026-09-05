from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from loom import db, strategies  # noqa: F401  (strategies import registers the strategy registry)
from loom.api.routers import action_links, backtests, insights, performance, portfolio, push, settings, signals, trading
from loom.api.routers import strategies as strategies_router
from loom.seed import seed_all_strategies


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
