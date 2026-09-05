"""Email notifications (story 58, 64, ADR-0012, ticket #41): the universal fallback channel —
works identically on every platform regardless of push permission or browser support. Pending-
approval emails carry a signed, single-use, short-expiry action link per signal (story 64); the
other three events (kill-switch, order-failed, daily-loss-limit) are account-wide, not tied to a
single signal, so they're informational only — there's no "approve/reject" action for them to
carry. `FakeEmailSender` is the default faked boundary, matching every other integration here."""

from __future__ import annotations

import logging
import secrets
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.models import Environment, Signal, SignedActionLink
from loom.settings import get_settings

logger = logging.getLogger("loom.notifications.email")

DEFAULT_LINK_TTL_HOURS = 48


class EmailSender(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, body_html: str) -> None:
        raise NotImplementedError


class FakeEmailSender(EmailSender):
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body_html: str) -> None:
        self.sent.append((to, subject, body_html))
        logger.info("(fake) email to %s: %s", to, subject)


class SmtpEmailSender(EmailSender):
    def __init__(self, host: str, port: int, username: str, password: str, from_email: str):
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.from_email = from_email

    def send(self, to: str, subject: str, body_html: str) -> None:
        import smtplib
        from email.mime.text import MIMEText

        message = MIMEText(body_html, "html")
        message["Subject"] = subject
        message["From"] = self.from_email
        message["To"] = to

        try:
            with smtplib.SMTP(self.host, self.port) as smtp:
                smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.sendmail(self.from_email, [to], message.as_string())
        except (smtplib.SMTPException, OSError) as exc:
            # A transient SMTP outage shouldn't turn a successful trading pass, approval, or
            # kill-switch action into a 500 — mirrors WebPushSender's per-target isolation below.
            logger.warning("email to %s failed: %s", to, exc)


def generate_action_link(session: Session, signal_id: str, action: str, ttl_hours: int = DEFAULT_LINK_TTL_HOURS) -> str:
    token = secrets.token_urlsafe(32)
    link = SignedActionLink(
        token=token,
        signal_id=signal_id,
        action=action,
        expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
    )
    session.add(link)
    session.commit()
    base_url = get_settings().api_base_url
    return f"{base_url}/action-links/{token}"


class ActionLinkError(Exception):
    pass


def consume_action_link(session: Session, token: str) -> SignedActionLink:
    """Marks the link used and returns it — raises if it's already been used or has expired
    (ticket #41 AC: a second use is rejected, expiry is enforced).

    Known v1 simplification: this is a check-then-act read/commit, not a `SELECT ... FOR UPDATE`
    or atomic conditional update — two near-simultaneous hits on the same token (e.g. an email
    security scanner's link pre-fetch racing the user's actual click) could both pass the
    `used_at is None` check before either commits. Low-likelihood for a single-user v1 deployment,
    but a real gap worth closing (e.g. an atomic `UPDATE ... WHERE used_at IS NULL RETURNING`)
    before this is exposed to untrusted recipients."""
    link = session.execute(select(SignedActionLink).where(SignedActionLink.token == token)).scalar_one_or_none()
    if link is None:
        raise ActionLinkError("unknown action link")
    if link.used_at is not None:
        raise ActionLinkError("this link has already been used")
    if link.expires_at < datetime.utcnow():
        raise ActionLinkError("this link has expired")
    link.used_at = datetime.utcnow()
    session.commit()
    return link


def send_pending_approval_email(session: Session, sender: EmailSender, to: str, signal: Signal) -> None:
    approve_url = generate_action_link(session, signal.id, "approve")
    reject_url = generate_action_link(session, signal.id, "reject")
    body = (
        f"<p>{signal.action.upper()} {signal.instrument} is pending your approval "
        f"(confidence {signal.confidence:.0%}).</p>"
        f'<p><a href="{approve_url}">Approve</a> &nbsp; <a href="{reject_url}">Reject</a></p>'
    )
    sender.send(to, f"Loom: {signal.instrument} pending approval", body)


def send_kill_switch_email(sender: EmailSender, to: str, environment: Environment, engaged: bool) -> None:
    state = "engaged" if engaged else "resumed"
    body = f"<p>The kill switch for {environment.value} has been {state}.</p>"
    sender.send(to, f"Loom: kill switch {state} ({environment.value})", body)


def send_order_failed_email(sender: EmailSender, to: str, signal: Signal, reason: str) -> None:
    body = f"<p>An order for {signal.action} {signal.instrument} failed: {reason}.</p>"
    sender.send(to, f"Loom: order failed for {signal.instrument}", body)


def send_daily_loss_limit_email(sender: EmailSender, to: str, environment: Environment, loss_pct: float) -> None:
    body = (
        f"<p>The daily loss limit for {environment.value} was breached (down {loss_pct:.1%} today) "
        "— the kill switch has been engaged automatically.</p>"
    )
    sender.send(to, f"Loom: daily loss limit hit ({environment.value})", body)
