"""Kill switch: current state is the most recent `KillSwitchEvent` row for an Environment — not
a local flag file. A file only reflects one process's local disk and can't be trusted across
Cloud Run's multiple stateless instances (each request can land on a different container, and
none of them share a filesystem or persist one across restarts); the database is the one thing
every instance actually shares. Checked by the execution layer immediately before every order
submission (CONTEXT.md). Scoped to the whole Environment (every Book plus Manual)."""

from sqlalchemy.orm import Session

from loom._global_flag import latest_state
from loom.models import Environment, KillSwitchEvent


def is_engaged(session: Session, environment: Environment) -> bool:
    return latest_state(session, KillSwitchEvent, "triggered", environment=environment)


def engage(session: Session, environment: Environment, actor: str = "user") -> None:
    session.add(KillSwitchEvent(environment=environment, triggered=True, actor=actor))
    session.commit()


def resume(session: Session, environment: Environment, actor: str = "user") -> None:
    session.add(KillSwitchEvent(environment=environment, triggered=False, actor=actor))
    session.commit()
