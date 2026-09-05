from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.api.deps import get_db
from loom.models import Environment, PushSubscription
from loom.settings import get_settings

router = APIRouter(prefix="/push", tags=["push"])


class PushSubscriptionIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    environment: str = "demo"


@router.get("/vapid-public-key")
def vapid_public_key():
    """Empty when no VAPID key pair is configured — the frontend should skip subscribing rather
    than call /push/subscribe with nothing to route pushes through (story 60)."""
    return {"public_key": get_settings().vapid_public_key or None}


@router.post("/subscribe")
def subscribe(body: PushSubscriptionIn, session: Session = Depends(get_db)):
    existing = session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    ).scalar_one_or_none()
    if existing is not None:
        return {"id": existing.id, "status": "already subscribed"}

    subscription = PushSubscription(
        environment=Environment(body.environment), endpoint=body.endpoint, p256dh=body.p256dh, auth=body.auth
    )
    session.add(subscription)
    session.commit()
    return {"id": subscription.id, "status": "subscribed"}


@router.post("/unsubscribe")
def unsubscribe(endpoint: str, session: Session = Depends(get_db)):
    existing = session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    ).scalar_one_or_none()
    if existing is not None:
        session.delete(existing)
        session.commit()
    return {"status": "unsubscribed"}
