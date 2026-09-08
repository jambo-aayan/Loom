"""Global live-trading gate (CONTEXT.md "Live trading gate"): a single on/off switch, independent
of any per-Strategy `live_enabled` flag, that must also be on before Loom will place a single live
Order. Off by default — Phase 1 launches demo-only and this gate is the deliberate step to leave
that phase, not a per-strategy setting.

Current state is the most recent `LiveTradingGateEvent` row, not a local flag file — a file can't
be trusted across Cloud Run's multiple stateless instances, which share no filesystem; the
database is what every instance actually shares."""

from sqlalchemy.orm import Session

from loom._global_flag import latest_state
from loom.models import LiveTradingGateEvent


def is_enabled(session: Session) -> bool:
    return latest_state(session, LiveTradingGateEvent, "enabled")


def enable(session: Session, actor: str = "user") -> None:
    session.add(LiveTradingGateEvent(enabled=True, actor=actor))
    session.commit()


def disable(session: Session, actor: str = "user") -> None:
    session.add(LiveTradingGateEvent(enabled=False, actor=actor))
    session.commit()
