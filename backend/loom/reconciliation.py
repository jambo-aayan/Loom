"""Manual Book reconciliation (story 36, ADR-0010, ticket #43): any position the live broker
reports that no strategy Book fully accounts for is attributed to the `Manual` Book.

There's deliberately no persisted "reconciliation event" or synthetic Order/Signal here — a
position Loom never placed has no Signal to attach an Order to, and fabricating one would corrupt
the audit trail (Order/Signal records are Loom's own decisions, not a mirror of the broker).
Instead this is computed fresh at query time from the broker's own position list minus what
`book_positions` already attributes to a strategy Book, so it's naturally idempotent and never
double-counts or reassigns strategy-owned quantity."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.execution.broker import BrokerClient
from loom.models import Book, Environment
from loom.strategy import PositionSnapshot
from loom.trading_pass import book_positions, get_or_create_book


def manual_positions(session: Session, environment: Environment, broker: BrokerClient) -> tuple[PositionSnapshot, ...]:
    strategy_books = session.execute(
        select(Book).where(Book.environment == environment, Book.strategy_id.isnot(None))
    ).scalars().all()

    attributed_quantity: dict[str, float] = {}
    for book in strategy_books:
        for snap in book_positions(session, book.id):
            attributed_quantity[snap.instrument] = attributed_quantity.get(snap.instrument, 0.0) + snap.quantity

    untracked = [
        pos for pos in broker.get_positions() if pos.quantity - attributed_quantity.get(pos.instrument, 0.0) > 1e-9
    ]
    if not untracked:
        return ()

    manual_book = get_or_create_book(session, None, environment, "Manual")
    session.commit()  # the Book row itself is real, persisted state — unlike the positions
    # below, which are recomputed fresh on every call and never written to the DB.
    return tuple(
        PositionSnapshot(
            instrument=pos.instrument,
            quantity=pos.quantity - attributed_quantity.get(pos.instrument, 0.0),
            average_price=pos.average_price,
            book_id=manual_book.id,
        )
        for pos in untracked
    )
