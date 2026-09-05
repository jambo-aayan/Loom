from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from loom.api.deps import get_broker, get_db, get_market_data_source
from loom.api.schemas import SignalOut
from loom.execution.broker import BrokerClient
from loom.market_data.base import MarketDataSource
from loom.models import Environment
from loom.trading_pass import run_trading_pass

router = APIRouter(prefix="/trading-pass", tags=["trading-pass"])

DEFAULT_UNIVERSE = ["VUSA.L", "VWRL.L", "TSLA", "NVDA"]


@router.post("/run", response_model=list[SignalOut])
def trigger_trading_pass(
    environment: str = "demo",
    session: Session = Depends(get_db),
    source: MarketDataSource = Depends(get_market_data_source),
):
    """CLI-triggerable via `loom trade-pass`; also exposed here for an on-demand "run now" in the
    dashboard (story 11, 12)."""
    env = Environment(environment)
    broker: BrokerClient = get_broker(env)
    universe = getattr(source, "universe", lambda: DEFAULT_UNIVERSE)()
    return run_trading_pass(env, session, broker, source, universe=universe)
