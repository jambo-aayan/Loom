"""Per-Book P&L (story 35, ticket #46): current market value and unrealized P&L for a Book's
open positions, computed from the market data source's own recent price history. There's no
separate "latest price" concept on `MarketDataSource` — a short-window `get_history` call already
gives us the most recent close, so this stays a pure function over the existing interface rather
than growing a new one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from loom.market_data.base import MarketDataSource
from loom.models import Book
from loom.strategy import PositionSnapshot

_LOOKBACK_DAYS = 14


@dataclass(frozen=True)
class BookPnl:
    book_id: str
    book_name: str
    strategy_key: str | None
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


def _latest_price(source: MarketDataSource, instrument: str, fallback: float) -> float:
    end = date.today()
    start = end - timedelta(days=_LOOKBACK_DAYS)
    history = source.get_history(instrument, start.isoformat(), end.isoformat())
    latest = history.latest
    return latest.close if latest is not None else fallback


def book_pnl(book: Book, positions: tuple[PositionSnapshot, ...], source: MarketDataSource) -> BookPnl | None:
    """None for a Book with no open positions — nothing to report, not a zero/NaN P&L."""
    if not positions:
        return None

    cost_basis = sum(p.quantity * p.average_price for p in positions)
    market_value = sum(p.quantity * _latest_price(source, p.instrument, p.average_price) for p in positions)
    unrealized_pnl = market_value - cost_basis
    # A zero cost basis (a free grant, say) has no meaningful "% gain" — 0.0 avoids division by
    # zero while staying a plain float the frontend can render without special-casing.
    unrealized_pnl_pct = unrealized_pnl / cost_basis if cost_basis > 0 else 0.0

    return BookPnl(
        book_id=book.id,
        book_name=book.name,
        strategy_key=book.strategy.key if book.strategy else None,
        cost_basis=cost_basis,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
    )
