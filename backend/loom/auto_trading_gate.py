"""Global auto-trading gate (CONTEXT.md "Auto-trading gate"): a single on/off switch controlling
whether any Strategy's Approval mode is allowed to auto-approve at all. Off by default. A
non-destructive circuit breaker, not a mutation of any Strategy's stored `approval_mode` — turning
this back on immediately restores each Strategy's own configured behavior.

Current state is the most recent `AutoTradingGateEvent` row, not a local flag file — a file can't
be trusted across Cloud Run's multiple stateless instances, which share no filesystem; the
database is what every instance actually shares."""

from sqlalchemy.orm import Session

from loom._global_flag import latest_state
from loom.models import AutoTradingGateEvent


def is_enabled(session: Session) -> bool:
    return latest_state(session, AutoTradingGateEvent, "enabled")


def enable(session: Session, actor: str = "user") -> None:
    session.add(AutoTradingGateEvent(enabled=True, actor=actor))
    session.commit()


def disable(session: Session, actor: str = "user") -> None:
    session.add(AutoTradingGateEvent(enabled=False, actor=actor))
    session.commit()
