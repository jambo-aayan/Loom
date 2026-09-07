"""Reconstructs closed round-trip trades (entry fill(s) matched FIFO against exit fill(s)) from a
Book's filled Orders — the real trade history evaluation metrics (#37) and the trade log (#28)
both need, going one level deeper than `trading_pass.book_positions` (which only tracks the
current net position, not historical closed trades)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.models import Order, OrderStatus, Signal


@dataclass
class ClosedTrade:
    instrument: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    quantity: float
    exit_order_id: str | None = None

    @property
    def pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def return_pct(self) -> float:
        return (self.exit_price - self.entry_price) / self.entry_price if self.entry_price else 0.0

    @property
    def hold_days(self) -> int:
        return max(0, (self.exit_date - self.entry_date).days)


@dataclass(frozen=True)
class BookedTrade:
    """What a single sell Order booked (CONTEXT.md "Trade") — one or more `ClosedTrade` FIFO lots
    that Order's fill closed, aggregated into one realized-P&L figure (story: "tell me what
    profit we're booking" the moment a sell executes)."""

    instrument: str
    quantity: float
    exit_price: float
    realized_pnl: float
    realized_pnl_pct: float
    closed_at: datetime | None


def aggregate_realized(closed: list[ClosedTrade]) -> tuple[float | None, float | None]:
    """(realized_pnl, realized_pnl_pct) for a group of `ClosedTrade` lots — e.g. every lot one
    sell Order closed. `None, None` for an empty group, distinct from a real zero P&L. The one
    place this math lives, so `Signal.booked_trade` and the Strategy trade log can't drift apart
    (ADR-0015's whole point)."""
    if not closed:
        return None, None
    realized_pnl = sum(t.pnl for t in closed)
    cost_basis = sum(t.entry_price * t.quantity for t in closed)
    realized_pnl_pct = realized_pnl / cost_basis if cost_basis else 0.0
    return realized_pnl, realized_pnl_pct


def booked_trade_for_signal(session: Session, signal: Signal) -> BookedTrade | None:
    """What a sell Signal's fill booked (CONTEXT.md "Trade") — None for anything but a filled
    sell. Lives here, not on `Signal` itself, since it's really a query over Order/Trade
    reconstruction data that Signal has no other reason to know how to run."""
    if signal.action != "sell":
        return None
    order = session.execute(
        select(Order).where(Order.signal_id == signal.id, Order.status == OrderStatus.filled)
    ).scalar_one_or_none()
    if order is None:
        return None

    closed = [t for t in reconstruct_closed_trades(session, signal.book_id) if t.exit_order_id == order.id]
    realized_pnl, realized_pnl_pct = aggregate_realized(closed)
    if realized_pnl is None:
        return None

    return BookedTrade(
        instrument=signal.instrument,
        quantity=sum(t.quantity for t in closed),
        exit_price=order.fill_price or 0.0,
        realized_pnl=realized_pnl,
        realized_pnl_pct=realized_pnl_pct,
        closed_at=order.filled_at,
    )


def reconstruct_closed_trades(session: Session, book_id: str) -> list[ClosedTrade]:
    orders = (
        session.execute(
            select(Order)
            .where(Order.book_id == book_id, Order.status == OrderStatus.filled)
            .order_by(Order.filled_at)
        )
        .scalars()
        .all()
    )

    # FIFO lots per instrument: a queue of [quantity_remaining, entry_price, entry_date].
    open_lots: dict[str, list[list]] = {}
    closed: list[ClosedTrade] = []

    for order in orders:
        signal = session.get(Signal, order.signal_id)
        if signal is None or order.fill_price is None or order.filled_at is None:
            continue
        instrument = signal.instrument
        lots = open_lots.setdefault(instrument, [])

        if signal.action in ("buy", "add"):
            lots.append([order.quantity, order.fill_price, order.filled_at])
            continue

        # A sell/exit closes FIFO against whatever lots are open, oldest first.
        remaining = order.quantity
        while remaining > 1e-9 and lots:
            lot_qty, entry_price, entry_date = lots[0]
            matched = min(lot_qty, remaining)
            closed.append(
                ClosedTrade(
                    instrument=instrument,
                    entry_date=entry_date,
                    exit_date=order.filled_at,
                    entry_price=entry_price,
                    exit_price=order.fill_price,
                    quantity=matched,
                    exit_order_id=order.id,
                )
            )
            lot_qty -= matched
            remaining -= matched
            if lot_qty <= 1e-9:
                lots.pop(0)
            else:
                lots[0][0] = lot_qty

    return closed
