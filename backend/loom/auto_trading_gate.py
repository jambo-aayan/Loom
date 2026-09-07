"""Global auto-trading gate (CONTEXT.md "Auto-trading gate"): a single on/off switch controlling
whether any Strategy's Approval mode is allowed to auto-approve at all. Off by default. A
non-destructive circuit breaker, not a mutation of any Strategy's stored `approval_mode` — turning
this back on immediately restores each Strategy's own configured behavior. Mirrors
killswitch.py's flag-file + event-log shape."""

from pathlib import Path

from sqlalchemy.orm import Session

from loom.models import AutoTradingGateEvent
from loom.settings import get_settings


def _flag_path() -> Path:
    return Path(get_settings().auto_trading_gate_path)


def is_enabled() -> bool:
    return _flag_path().exists()


def enable(session: Session, actor: str = "user") -> None:
    _flag_path().touch()
    session.add(AutoTradingGateEvent(enabled=True, actor=actor))
    session.commit()


def disable(session: Session, actor: str = "user") -> None:
    path = _flag_path()
    if path.exists():
        path.unlink()
    session.add(AutoTradingGateEvent(enabled=False, actor=actor))
    session.commit()
