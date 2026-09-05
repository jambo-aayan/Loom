from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from loom import killswitch
from loom.api.deps import get_db
from loom.api.schemas import KillSwitchOut
from loom.models import Environment

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/kill-switch", response_model=KillSwitchOut)
def get_kill_switch(environment: str = "demo"):
    env = Environment(environment)
    return KillSwitchOut(environment=environment, engaged=killswitch.is_engaged(env))


@router.post("/kill-switch/engage", response_model=KillSwitchOut)
def engage_kill_switch(environment: str = "demo", session: Session = Depends(get_db)):
    env = Environment(environment)
    killswitch.engage(session, env)
    return KillSwitchOut(environment=environment, engaged=True)


@router.post("/kill-switch/resume", response_model=KillSwitchOut)
def resume_kill_switch(environment: str = "demo", session: Session = Depends(get_db)):
    env = Environment(environment)
    killswitch.resume(session, env)
    return KillSwitchOut(environment=environment, engaged=False)
