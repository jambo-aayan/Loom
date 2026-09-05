from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from loom import killswitch
from loom.api.deps import get_broker, get_db, get_email_sender, get_insight_generator, get_market_data_source
from loom.api.schemas import InsightOut, SignalDecisionIn, SignalOut
from loom.insight.generator import InsightGenerator
from loom.insight.screening import generate_screening_insight, run_screening_job
from loom.market_data.base import MarketDataSource
from loom.models import Environment, Insight, OrderStatus, Signal, SignalStatus
from loom.notifications.dispatch import notify_order_failed
from loom.notifications.email import EmailSender
from loom.settings import get_settings
from loom.trading_pass import approve_signal, reject_signal

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[SignalOut])
def list_signals(
    environment: str = "demo",
    status: str | None = None,
    session: Session = Depends(get_db),
):
    query = select(Signal).where(Signal.environment == Environment(environment))
    if status:
        query = query.where(Signal.status == SignalStatus(status))
    query = query.order_by(Signal.created_at.desc())
    return session.execute(query).scalars().all()


@router.get("/{signal_id}", response_model=SignalOut)
def get_signal(signal_id: str, session: Session = Depends(get_db)):
    signal = session.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(404, "signal not found")
    return signal


@router.get("/{signal_id}/insights", response_model=list[InsightOut])
def list_signal_insights(signal_id: str, session: Session = Depends(get_db)):
    return session.execute(select(Insight).where(Insight.signal_id == signal_id)).scalars().all()


@router.post("/{signal_id}/screen", response_model=InsightOut)
def screen_signal(
    signal_id: str,
    session: Session = Depends(get_db),
    generator: InsightGenerator = Depends(get_insight_generator),
):
    """Generates the cheap screening-tier Insight for a pending signal (story 30, 54)."""
    signal = session.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(404, "signal not found")
    return generate_screening_insight(session, signal, generator)


@router.post("/screen-pending", response_model=list[InsightOut])
def screen_pending(
    environment: str = "demo",
    session: Session = Depends(get_db),
    generator: InsightGenerator = Depends(get_insight_generator),
):
    """The screening-tier Insight job (story 30, 52, 54): runs on every signal candidate that
    doesn't have one yet, as its own job — deliberately separate from /trading-pass/run, so it
    can be scheduled independently (e.g. `loom screen-insights`) without a slow LLM call ever
    blocking order-related work."""
    return run_screening_job(session, generator, environment=Environment(environment))


@router.post("/{signal_id}/approve", response_model=SignalOut)
def approve(
    signal_id: str,
    body: SignalDecisionIn,
    session: Session = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender),
):
    signal = session.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(404, "signal not found")
    if signal.status not in (SignalStatus.pending_approval, SignalStatus.proposed):
        raise HTTPException(409, f"signal is already {signal.status.value}")
    broker = get_broker(signal.environment)  # the signal's own environment decides the broker
    order = approve_signal(session, signal, broker, note=body.note)

    if order.status == OrderStatus.failed and not killswitch.is_engaged(signal.environment):
        notify_order_failed(email_sender, get_settings().notify_email, signal, "risk/sizing check rejected the order")
    return signal


@router.post("/{signal_id}/reject", response_model=SignalOut)
def reject(
    signal_id: str,
    body: SignalDecisionIn,
    session: Session = Depends(get_db),
    source: MarketDataSource = Depends(get_market_data_source),
):
    signal = session.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(404, "signal not found")
    if signal.status not in (SignalStatus.pending_approval, SignalStatus.proposed):
        raise HTTPException(409, f"signal is already {signal.status.value}")
    reject_signal(session, signal, note=body.note, market_data_source=source)
    return signal
