from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from loom import auto_trading_gate, exit_enforcement, killswitch, live_trading_gate
from loom.api.deps import get_db, get_email_sender
from loom.api.schemas import AutoTradingGateOut, ExitEnforcementOut, KillSwitchOut, LiveTradingGateOut
from loom.models import Environment
from loom.notifications.dispatch import notify_kill_switch_engaged
from loom.notifications.email import EmailSender
from loom.settings import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/kill-switch", response_model=KillSwitchOut)
def get_kill_switch(environment: str = "demo", session: Session = Depends(get_db)):
    env = Environment(environment)
    return KillSwitchOut(environment=environment, engaged=killswitch.is_engaged(session, env))


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


@router.get("/live-trading-gate", response_model=LiveTradingGateOut)
def get_live_trading_gate(session: Session = Depends(get_db)):
    return LiveTradingGateOut(enabled=live_trading_gate.is_enabled(session))


@router.post("/live-trading-gate/enable", response_model=LiveTradingGateOut)
def enable_live_trading_gate(session: Session = Depends(get_db)):
    live_trading_gate.enable(session)
    return LiveTradingGateOut(enabled=True)


@router.post("/live-trading-gate/disable", response_model=LiveTradingGateOut)
def disable_live_trading_gate(session: Session = Depends(get_db)):
    live_trading_gate.disable(session)
    return LiveTradingGateOut(enabled=False)


@router.get("/exit-enforcement", response_model=ExitEnforcementOut)
def get_exit_enforcement(environment: str = "demo", session: Session = Depends(get_db)):
    env = Environment(environment)
    return ExitEnforcementOut(environment=environment, enforcing=exit_enforcement.is_enforcing(session, env))


@router.post("/exit-enforcement/enable", response_model=ExitEnforcementOut)
def enable_exit_enforcement(environment: str = "demo", session: Session = Depends(get_db)):
    """Stop observing and start acting (#58). Deliberately explicit: enforcement ships dry-run
    first because no exit parameter in the roster has ever had feedback, so turning it on could
    close existing positions — not because enforcement is wrong but because a parameter is."""
    exit_enforcement.enable(session, Environment(environment))
    return ExitEnforcementOut(environment=environment, enforcing=True)


@router.post("/exit-enforcement/disable", response_model=ExitEnforcementOut)
def disable_exit_enforcement(environment: str = "demo", session: Session = Depends(get_db)):
    exit_enforcement.disable(session, Environment(environment))
    return ExitEnforcementOut(environment=environment, enforcing=False)


@router.get("/auto-trading-gate", response_model=AutoTradingGateOut)
def get_auto_trading_gate(session: Session = Depends(get_db)):
    return AutoTradingGateOut(enabled=auto_trading_gate.is_enabled(session))


@router.post("/auto-trading-gate/enable", response_model=AutoTradingGateOut)
def enable_auto_trading_gate(session: Session = Depends(get_db)):
    auto_trading_gate.enable(session)
    return AutoTradingGateOut(enabled=True)


@router.post("/auto-trading-gate/disable", response_model=AutoTradingGateOut)
def disable_auto_trading_gate(session: Session = Depends(get_db)):
    auto_trading_gate.disable(session)
    return AutoTradingGateOut(enabled=False)
