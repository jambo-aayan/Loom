from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from loom import killswitch
from loom.api.deps import get_db, get_email_sender
from loom.api.schemas import KillSwitchOut
from loom.models import Environment
from loom.notifications.dispatch import notify_kill_switch_engaged
from loom.notifications.email import EmailSender
from loom.settings import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/kill-switch", response_model=KillSwitchOut)
def get_kill_switch(environment: str = "demo"):
    env = Environment(environment)
    return KillSwitchOut(environment=environment, engaged=killswitch.is_engaged(env))


@router.post("/kill-switch/engage", response_model=KillSwitchOut)
def engage_kill_switch(
    environment: str = "demo", session: Session = Depends(get_db), email_sender: EmailSender = Depends(get_email_sender)
):
    env = Environment(environment)
    killswitch.engage(session, env)
    notify_kill_switch_engaged(email_sender, get_settings().notify_email, env, engaged=True)
    return KillSwitchOut(environment=environment, engaged=True)


@router.post("/kill-switch/resume", response_model=KillSwitchOut)
def resume_kill_switch(
    environment: str = "demo", session: Session = Depends(get_db), email_sender: EmailSender = Depends(get_email_sender)
):
    env = Environment(environment)
    killswitch.resume(session, env)
    notify_kill_switch_engaged(email_sender, get_settings().notify_email, env, engaged=False)
    return KillSwitchOut(environment=environment, engaged=False)
