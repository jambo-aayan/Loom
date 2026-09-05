from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.api.deps import get_broker, get_db, get_insight_generator, get_market_data_source
from loom.api.schemas import AskIn, InsightOut
from loom.insight.generator import InsightGenerator
from loom.market_data.base import MarketDataSource
from loom.models import Book, Environment, Insight, InsightTier, Signal, SignalStatus
from loom.models import Strategy as StrategyModel
from loom.reconciliation import manual_positions
from loom.trading_pass import book_positions

router = APIRouter(prefix="/insights", tags=["insights"])

_PERIOD_DAYS = {"daily": 1, "weekly": 7}


@router.get("/digest")
def digest(environment: str = "demo", period: str = "daily", session: Session = Depends(get_db)):
    """A rolled-up summary of what fired and what the screening tier is watching (story 55, 56,
    ticket #42) — built entirely from the screening-tier Insight data #30 already generates, no
    new generation tier."""
    if period not in _PERIOD_DAYS:
        raise HTTPException(400, f"period must be one of {list(_PERIOD_DAYS)}")
    since = datetime.utcnow() - timedelta(days=_PERIOD_DAYS[period])

    insights = (
        session.execute(
            select(Insight)
            .where(Insight.tier == InsightTier.screening, Insight.created_at >= since)
            .order_by(Insight.created_at.desc())
        )
        .scalars()
        .all()
    )

    fired = []
    still_watching = []
    for insight in insights:
        signal = session.get(Signal, insight.signal_id)
        if signal is None or signal.environment != Environment(environment):
            continue
        strategy = session.get(StrategyModel, signal.strategy_id)
        entry = {
            "signal_id": signal.id,
            "strategy_name": strategy.name if strategy else None,
            "instrument": signal.instrument,
            "action": signal.action,
            "confidence": signal.confidence,
            "status": signal.status.value if hasattr(signal.status, "value") else signal.status,
            "insight": insight.content,
            "created_at": insight.created_at,
        }
        if signal.status == SignalStatus.pending_approval:
            still_watching.append(entry)
        else:
            fired.append(entry)

    return {
        "environment": environment,
        "period": period,
        "since": since.isoformat(),
        "fired": fired,
        "still_watching": still_watching,
    }


@router.post("/positions/{book_id}/{instrument}", response_model=InsightOut)
def position_commentary(
    book_id: str,
    instrument: str,
    session: Session = Depends(get_db),
    generator: InsightGenerator = Depends(get_insight_generator),
):
    """Advisory commentary about any held position — including `Manual` and other strategies'
    Books, not just the bot's own signals (story 37, ticket #44)."""
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "book not found")

    if book.strategy_id is not None:
        candidates = book_positions(session, book.id)
    else:
        candidates = manual_positions(session, book.environment, get_broker(book.environment))
    snap = next((s for s in candidates if s.instrument == instrument), None)
    if snap is None:
        raise HTTPException(404, f"no open {instrument} position in book {book_id}")

    content = generator.generate_position_commentary(instrument, book.name, snap.quantity, snap.average_price)
    insight = Insight(book_id=book.id, instrument=instrument, tier=InsightTier.position, content=content)
    session.add(insight)
    session.commit()
    session.refresh(insight)
    return insight


@router.post("/ask")
def ask(body: AskIn, generator: InsightGenerator = Depends(get_insight_generator)):
    """On-demand "ask about this stock / this macro topic" research (story 51) — free-form,
    advisory-only, structurally incapable of becoming an order (story 53): purely a generated
    answer, no Signal, Order, or approval-pipeline side effect of any kind."""
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "question must not be blank")
    answer = generator.answer_question(question, body.instrument)
    return {"question": question, "instrument": body.instrument, "answer": answer}


@router.get("/signals/{signal_id}/chart")
def signal_chart(
    signal_id: str,
    window_days: int = 30,
    session: Session = Depends(get_db),
    source: MarketDataSource = Depends(get_market_data_source),
):
    """The instrument's price chart around a signal's trigger, with the trigger point itself
    annotated (story 55: "marked directly on the price chart, not just described in text")."""
    signal = session.get(Signal, signal_id)
    if signal is None:
        raise HTTPException(404, "signal not found")

    trigger_date = signal.created_at.date()
    start = (trigger_date - timedelta(days=window_days)).isoformat()
    end = (trigger_date + timedelta(days=window_days)).isoformat()
    history = source.get_history(signal.instrument, start, end)

    return {
        "instrument": signal.instrument,
        "bars": [
            {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close} for b in history.bars
        ],
        "trigger": {
            "date": trigger_date.isoformat(),
            "price": signal.reference_price,
            "action": signal.action,
            "reasoning": next(
                (
                    i.content
                    for i in session.execute(
                        select(Insight)
                        .where(Insight.signal_id == signal_id, Insight.tier == InsightTier.screening)
                        .order_by(Insight.created_at.desc())
                    ).scalars()
                ),
                None,
            ),
        },
    }
