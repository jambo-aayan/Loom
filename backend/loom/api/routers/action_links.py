from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from loom.api.deps import get_broker, get_db, get_market_data_source
from loom.market_data.base import MarketDataSource
from loom.models import Signal, SignalStatus
from loom.notifications.email import ActionLinkError, consume_action_link
from loom.trading_pass import approve_signal, reject_signal

router = APIRouter(prefix="/action-links", tags=["action-links"])


def _page(message: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html><body style='font-family: sans-serif; padding: 2rem;'><p>{message}</p></body></html>"
    )


@router.get("/{token}")
def consume(
    token: str,
    session: Session = Depends(get_db),
    source: MarketDataSource = Depends(get_market_data_source),
):
    """A one-tap email action link (story 64, ticket #41): no login, no app open — the same
    approve/reject path as the dashboard (#25), re-checked server-side, single-use, short-expiry."""
    try:
        link = consume_action_link(session, token)
    except ActionLinkError as exc:
        return _page(str(exc))

    signal = session.get(Signal, link.signal_id)
    if signal is None:
        return _page("That signal no longer exists.")
    if signal.status not in (SignalStatus.pending_approval, SignalStatus.proposed):
        return _page(f"{signal.instrument} was already {signal.status.value} — no action taken.")

    if link.action == "approve":
        broker = get_broker(signal.environment)
        approve_signal(session, signal, broker, note="Approved via email action link")
        return _page(f"Approved: {signal.action} {signal.instrument}.")
    else:
        reject_signal(session, signal, note="Rejected via email action link", market_data_source=source)
        return _page(f"Rejected: {signal.action} {signal.instrument}.")
