from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.api.deps import get_db, get_fundamentals_provider, get_market_data_source
from loom.correlation import compute_correlation_matrix
from loom.evaluation import compute_metrics, equity_and_benchmark_curve
from loom.fundamentals import FundamentalsProvider, filter_by_sector
from loom.market_data.base import MarketDataSource
from loom.models import Book, Environment
from loom.trade_reconstruction import ClosedTrade, reconstruct_closed_trades

router = APIRouter(tags=["performance"])


def _filter_trades(
    trades: list[ClosedTrade],
    instrument: str | None,
    sector: str | None,
    fundamentals: FundamentalsProvider,
) -> list[ClosedTrade]:
    """Slices closed trades by instrument and/or sector/industry (story 72)."""
    if instrument:
        trades = [t for t in trades if t.instrument == instrument]
    if sector:
        trades = filter_by_sector(trades, lambda t: t.instrument, sector, fundamentals)
    return trades


@router.get("/books")
def list_books(environment: str = "demo", session: Session = Depends(get_db)):
    books = session.execute(select(Book).where(Book.environment == Environment(environment))).scalars().all()
    return [
        {
            "id": b.id,
            "name": b.name,
            "strategy_id": b.strategy_id,
            "strategy_key": b.strategy.key if b.strategy else None,
        }
        for b in books
    ]


@router.get("/performance/books/{book_id}")
def book_performance(
    book_id: str,
    instrument: str | None = None,
    sector: str | None = None,
    session: Session = Depends(get_db),
    source: MarketDataSource = Depends(get_market_data_source),
    fundamentals: FundamentalsProvider = Depends(get_fundamentals_provider),
):
    book = session.get(Book, book_id)
    if book is None:
        raise HTTPException(404, "book not found")
    trades = _filter_trades(reconstruct_closed_trades(session, book_id), instrument, sector, fundamentals)
    return {
        "book_id": book_id,
        "book_name": book.name,
        "metrics": compute_metrics(trades),
        "curve": equity_and_benchmark_curve(trades, source),
    }


@router.get("/performance")
def aggregate_performance(
    environment: str = "demo",
    instrument: str | None = None,
    sector: str | None = None,
    session: Session = Depends(get_db),
    source: MarketDataSource = Depends(get_market_data_source),
    fundamentals: FundamentalsProvider = Depends(get_fundamentals_provider),
):
    """Every performance chart plotted against a benchmark over the same period (story 71), in
    aggregate across every strategy's Book plus Manual (story 70), sliceable by instrument and
    sector/industry in addition to by Book (story 72)."""
    books = session.execute(select(Book).where(Book.environment == Environment(environment))).scalars().all()
    trades_by_book = {
        book.id: _filter_trades(reconstruct_closed_trades(session, book.id), instrument, sector, fundamentals)
        for book in books
    }
    all_trades = [trade for trades in trades_by_book.values() for trade in trades]

    per_book = [
        {
            "book_id": book.id,
            "book_name": book.name,
            "strategy_key": book.strategy.key if book.strategy else None,
            "metrics": compute_metrics(trades_by_book[book.id]),
        }
        for book in books
    ]

    return {
        "environment": environment,
        "aggregate_metrics": compute_metrics(all_trades),
        "aggregate_curve": equity_and_benchmark_curve(all_trades, source),
        "per_book": per_book,
    }


@router.get("/performance/correlation")
def book_correlation(environment: str = "demo", session: Session = Depends(get_db)):
    """Are these strategies actually diversifying, or all moving together — pairwise correlation
    of weekly realized P&L across every Book (five strategies + Manual), story 72."""
    books = session.execute(select(Book).where(Book.environment == Environment(environment))).scalars().all()
    trades_by_book = {book.id: reconstruct_closed_trades(session, book.id) for book in books}
    return compute_correlation_matrix([(b.id, b.name) for b in books], trades_by_book)
