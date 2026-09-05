from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.api.deps import get_broker, get_db, get_fundamentals_provider
from loom.api.schemas import OverviewOut, PositionOut, SignalOut
from loom.fundamentals import FundamentalsProvider, filter_by_sector
from loom.models import Book, Environment, Signal, SignalStatus
from loom.reconciliation import manual_positions
from loom.trading_pass import book_positions

router = APIRouter(tags=["portfolio"])


@router.get("/overview", response_model=OverviewOut)
def overview(environment: str = "demo", session: Session = Depends(get_db)):
    env = Environment(environment)
    broker = get_broker(env)
    books = session.execute(select(Book).where(Book.environment == env)).scalars().all()

    positions: list[PositionOut] = []
    for book in books:
        for snap in book_positions(session, book.id):
            positions.append(
                PositionOut(
                    book_id=book.id,
                    book_name=book.name,
                    strategy_key=book.strategy.key if book.strategy else None,
                    instrument=snap.instrument,
                    quantity=snap.quantity,
                    average_price=snap.average_price,
                )
            )

    for snap in manual_positions(session, env, broker):
        positions.append(
            PositionOut(
                book_id=snap.book_id,
                book_name="Manual",
                strategy_key=None,
                instrument=snap.instrument,
                quantity=snap.quantity,
                average_price=snap.average_price,
            )
        )

    return OverviewOut(environment=environment, cash=broker.get_cash(), positions=positions)


_DECIDED_STATUSES = (
    SignalStatus.approved,
    SignalStatus.rejected,
    SignalStatus.expired,
    SignalStatus.executed,
)


@router.get("/history", response_model=list[SignalOut])
def history(
    environment: str = "demo",
    instrument: str | None = None,
    sector: str | None = None,
    session: Session = Depends(get_db),
    fundamentals: FundamentalsProvider = Depends(get_fundamentals_provider),
):
    """Every past decision with its actual outcome (if executed) or counterfactual outcome (if
    not), side by side with any note — story 69. Sliceable by instrument and by sector/industry,
    in addition to by Book (story 72)."""
    query = (
        select(Signal)
        .where(Signal.environment == Environment(environment), Signal.status.in_(_DECIDED_STATUSES))
        .order_by(Signal.decided_at.desc().nulls_last(), Signal.created_at.desc())
    )
    if instrument:
        query = query.where(Signal.instrument == instrument)
    signals = list(session.execute(query).scalars().all())

    if sector:
        signals = filter_by_sector(signals, lambda s: s.instrument, sector, fundamentals)

    return signals
