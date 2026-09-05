"""Web Push (story 60, ADR-0012, ticket #39): VAPID-signed pushes to per-device subscriptions.
`FakePushSender` (no VAPID keys configured) is the default — the same "faked external boundary"
pattern every other integration in this app follows; it never raises, just records what it would
have sent, so local dev and tests never depend on a real push service."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger("loom.notifications.push")


@dataclass
class PushTarget:
    endpoint: str
    p256dh: str
    auth: str


class PushSender(ABC):
    @abstractmethod
    def send(self, target: PushTarget, payload: dict) -> None:
        raise NotImplementedError


class FakePushSender(PushSender):
    def __init__(self) -> None:
        self.sent: list[tuple[PushTarget, dict]] = []

    def send(self, target: PushTarget, payload: dict) -> None:
        self.sent.append((target, payload))
        logger.info("(fake) push to %s: %s", target.endpoint, payload)


class WebPushSender(PushSender):
    def __init__(self, vapid_private_key: str, vapid_subject: str):
        self.vapid_private_key = vapid_private_key
        self.vapid_claims = {"sub": vapid_subject}

    def send(self, target: PushTarget, payload: dict) -> None:
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info={
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=self.vapid_private_key,
                vapid_claims=dict(self.vapid_claims),
            )
        except WebPushException as exc:
            # An expired/unsubscribed device is routine, not a trading-pass failure — log and
            # move on rather than letting one stale subscription break the whole notify step.
            logger.warning("push to %s failed: %s", target.endpoint, exc)


def build_signal_push_payload(signal_id: str, instrument: str, action: str, confidence: float) -> dict:
    """Android's service worker renders Approve/Reject action buttons from this payload's
    `actions`; both post straight back to the approve/reject endpoint (story 63, 65) — no app
    open required."""
    return {
        "title": f"{action.upper()} {instrument}?",
        "body": f"Confidence {confidence:.0%} — tap to decide, or use the buttons below.",
        "signal_id": signal_id,
        "actions": [
            {"action": "approve", "title": "Approve"},
            {"action": "reject", "title": "Reject"},
        ],
    }
