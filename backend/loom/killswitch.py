"""Kill switch: a local flag file, checked by the execution layer immediately before every
order submission (CONTEXT.md). Scoped to the whole Environment (every Book plus Manual)."""

from pathlib import Path

from sqlalchemy.orm import Session

from loom.models import Environment, KillSwitchEvent
from loom.settings import get_settings


def _flag_path(environment: Environment) -> Path:
    base = Path(get_settings().kill_switch_path)
    return base.parent / f"{base.name}.{environment.value}"


def is_engaged(environment: Environment) -> bool:
    return _flag_path(environment).exists()


def engage(session: Session, environment: Environment, actor: str = "user") -> None:
    _flag_path(environment).touch()
    session.add(KillSwitchEvent(environment=environment, triggered=True, actor=actor))
    session.commit()


def resume(session: Session, environment: Environment, actor: str = "user") -> None:
    path = _flag_path(environment)
    if path.exists():
        path.unlink()
    session.add(KillSwitchEvent(environment=environment, triggered=False, actor=actor))
    session.commit()
