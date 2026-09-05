from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from loom import killswitch
from loom.api.deps import get_broker, get_db, get_email_sender, get_market_data_source, get_push_sender
from loom.api.schemas import SignalOut
from loom.daily_loss import check_daily_loss_limit
from loom.execution.broker import BrokerClient
from loom.market_data.base import MarketDataSource
from loom.models import Environment
from loom.notifications.dispatch import (
    notify_daily_loss_limit,
    notify_failed_auto_approvals,
    notify_new_signals,
)
from loom.notifications.email import EmailSender
from loom.notifications.push import PushSender
from loom.settings import get_settings
from loom.trading_pass import run_trading_pass

router = APIRouter(prefix="/trading-pass", tags=["trading-pass"])

DEFAULT_UNIVERSE = ["VUSA.L", "VWRL.L", "TSLA", "NVDA"]


@router.post("/run", response_model=list[SignalOut])
def trigger_trading_pass(
    environment: str = "demo",
    session: Session = Depends(get_db),
    source: MarketDataSource = Depends(get_market_data_source),
    push_sender: PushSender = Depends(get_push_sender),
    email_sender: EmailSender = Depends(get_email_sender),
):
    """CLI-triggerable via `loom trade-pass`; also exposed here for an on-demand "run now" in the
    dashboard (story 11, 12)."""
    env = Environment(environment)
    broker: BrokerClient = get_broker(env)
    to_email = get_settings().notify_email

    was_engaged = killswitch.is_engaged(env)
    breached, loss_pct = check_daily_loss_limit(session, env, broker)
    if breached and not was_engaged:
        killswitch.engage(session, env, actor="daily-loss-limit")
        notify_daily_loss_limit(email_sender, to_email, env, loss_pct)

    universe = getattr(source, "universe", lambda: DEFAULT_UNIVERSE)()
    signals = run_trading_pass(env, session, broker, source, universe=universe)

    notify_new_signals(session, signals, push_sender, email_sender, to_email)
    notify_failed_auto_approvals(session, signals, env, email_sender, to_email)
    return signals
