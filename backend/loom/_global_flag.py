"""Shared query behind the kill switch and the two global trading gates
(killswitch.py, live_trading_gate.py, auto_trading_gate.py): each flag's current state is the
most recent row in its own append-only event table (never a local file — see those modules'
docstrings for why). This is the one place that "latest row wins" query lives, so the three
otherwise-independent, deliberately-thin wrapper modules can't drift on how they read it."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


def latest_state(session: Session, model: Any, state_field: str, **filters: object) -> bool:
    """`model` is any mapped class with an `at: DateTime` column — Any rather than a narrower
    bound since SQLAlchemy's declarative base doesn't itself carry that shape statically."""
    query: Any = select(model)
    for field, value in filters.items():
        query = query.where(getattr(model, field) == value)
    query = query.order_by(model.at.desc())
    latest = session.execute(query).scalars().first()
    return bool(getattr(latest, state_field)) if latest is not None else False
