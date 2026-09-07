"""Global live-trading gate (CONTEXT.md "Live trading gate"): a single on/off switch, independent
of any per-Strategy `live_enabled` flag, that must also be on before Loom will place a single live
Order. Off by default — Phase 1 launches demo-only and this gate is the deliberate step to leave
that phase, not a per-strategy setting. Mirrors killswitch.py's flag-file + event-log shape."""

from pathlib import Path

from sqlalchemy.orm import Session

from loom.models import LiveTradingGateEvent
from loom.settings import get_settings


def _flag_path() -> Path:
    return Path(get_settings().live_trading_gate_path)


def is_enabled() -> bool:
    return _flag_path().exists()


def enable(session: Session, actor: str = "user") -> None:
    _flag_path().touch()
    session.add(LiveTradingGateEvent(enabled=True, actor=actor))
    session.commit()


def disable(session: Session, actor: str = "user") -> None:
    path = _flag_path()
    if path.exists():
        path.unlink()
    session.add(LiveTradingGateEvent(enabled=False, actor=actor))
    session.commit()
