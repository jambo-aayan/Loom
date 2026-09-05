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

    @property
    def pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def return_pct(self) -> float:
        return (self.exit_price - self.entry_price) / self.entry_price if self.entry_price else 0.0

    @property
    def hold_days(self) -> int:
        return max(0, (self.exit_date - self.entry_date).days)


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
                )
            )
            lot_qty -= matched
            remaining -= matched
            if lot_qty <= 1e-9:
                lots.pop(0)
            else:
                lots[0][0] = lot_qty

    return closed
