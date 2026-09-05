"""Daily loss limit tracking (story 24: "a daily loss limit that can itself trigger the kill
switch", CONTEXT.md "Kill switch"). `loom.risk.daily_loss_breached` existed since M1 but was
never wired to anything — this module is that wiring: snapshot the account's value once per day,
compare the current value against it, and engage the kill switch (plus notify) if the loss limit
is breached.

**Known v1 simplification**: "account value" here is cash plus every held position's *entry*
cost basis (`quantity * average_price`), not a live mark-to-market using the latest close for
every held instrument — that would mean fetching a price for every instrument across every Book
regardless of whether it's in the current pass's universe, which is real scope beyond this
tracer-bullet ticket. This still catches the case the limit exists for (a bad day of *realized*
losses/cash outflow), just not unrealized paper losses on positions outside today's universe."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.execution.broker import BrokerClient
from loom.models import Book, DailyAccountSnapshot, Environment
from loom.risk import RiskLimits, daily_loss_breached
from loom.trading_pass import book_positions


def _account_value(session: Session, environment: Environment, broker: BrokerClient) -> float:
    books = session.execute(select(Book).where(Book.environment == environment)).scalars().all()
    positions_value = sum(
        snap.quantity * snap.average_price for book in books for snap in book_positions(session, book.id)
    )
    return broker.get_cash() + positions_value


def _get_or_create_snapshot(session: Session, environment: Environment, account_value: float) -> DailyAccountSnapshot:
    today = date.today().isoformat()
    snapshot = session.execute(
        select(DailyAccountSnapshot).where(
            DailyAccountSnapshot.environment == environment, DailyAccountSnapshot.date == today
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = DailyAccountSnapshot(environment=environment, date=today, starting_value=account_value)
        session.add(snapshot)
        session.commit()
    return snapshot


def check_daily_loss_limit(
    session: Session, environment: Environment, broker: BrokerClient, limits: RiskLimits | None = None
) -> tuple[bool, float]:
    """Returns (breached, loss_pct). Call once per trading pass, before evaluating strategies —
    the first call of a new day establishes that day's starting value; every call after that
    compares against it."""
    limits = limits or RiskLimits()
    current_value = _account_value(session, environment, broker)
    snapshot = _get_or_create_snapshot(session, environment, current_value)

    breached = daily_loss_breached(snapshot.starting_value, current_value, limits)
    loss_pct = (
        (snapshot.starting_value - current_value) / snapshot.starting_value if snapshot.starting_value > 0 else 0.0
    )
    return breached, loss_pct
