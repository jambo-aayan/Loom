"""Whether an `Environment`'s exit layer acts, or only observes (#58, ADR-0018).

Off by default. Enforcement ships dry-run first: every exit parameter in the roster was chosen
while nothing enforced it, so none has ever had feedback, and turning enforcement straight on
could close existing positions — not because enforcement is wrong but because a parameter is
(gap analysis D0). Flipping it is a deliberate, recorded act, never a side effect of a deploy.

Distinct from the `Kill switch`, which halts order submission entirely and outranks this, and
from the `Live trading gate`, which decides whether the `live` Environment runs at all.
"""

from sqlalchemy.orm import Session

from loom._global_flag import latest_state
from loom.models import Environment, ExitEnforcementEvent


def is_enforcing(session: Session, environment: Environment) -> bool:
    """False until explicitly enabled — a fresh database observes rather than acts."""
    return latest_state(session, ExitEnforcementEvent, "enforcing", environment=environment)


def enable(session: Session, environment: Environment, actor: str = "user") -> None:
    session.add(ExitEnforcementEvent(environment=environment, enforcing=True, actor=actor))
    session.commit()


def disable(session: Session, environment: Environment, actor: str = "user") -> None:
    session.add(ExitEnforcementEvent(environment=environment, enforcing=False, actor=actor))
    session.commit()
