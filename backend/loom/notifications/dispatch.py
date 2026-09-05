"""Orchestrates who gets notified about what. Deliberately a thin layer *outside*
`loom.trading_pass`'s core functions (run_trading_pass, execute_signal, killswitch.engage) rather
than baked into them — those are exercised by ~130 existing tests as pure state-machine
transitions, and notification delivery is a side effect the CLI/API call sites opt into after
the fact, the same way a caller opts into a specific BrokerClient or MarketDataSource."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom import killswitch
from loom.models import Environment, Order, OrderStatus, PushSubscription, Signal, SignalStatus
from loom.models import Strategy as StrategyModel
from loom.notifications.email import (
    EmailSender,
    send_daily_loss_limit_email,
    send_kill_switch_email,
    send_order_failed_email,
    send_pending_approval_email,
)
from loom.notifications.push import PushSender, PushTarget, build_signal_push_payload


def notify_new_signals(
    session: Session,
    signals: list[Signal],
    push_sender: PushSender,
    email_sender: EmailSender,
    to_email: str,
) -> None:
    """Pending-approval signals always get the email fallback (story 58); a push additionally
    fires only once the signal's own strategy Notify threshold is cleared (story 62) — a signal
    can need approval without being urgent enough to interrupt the user for."""
    pending = [s for s in signals if s.status == SignalStatus.pending_approval]
    if not pending:
        return

    subscriptions = session.execute(
        select(PushSubscription).where(PushSubscription.environment == pending[0].environment)
    ).scalars().all()

    for signal in pending:
        send_pending_approval_email(session, email_sender, to_email, signal)

        strategy = session.get(StrategyModel, signal.strategy_id)
        if strategy is not None and signal.confidence >= strategy.notify_threshold:
            payload = build_signal_push_payload(signal.id, signal.instrument, signal.action, signal.confidence)
            for sub in subscriptions:
                push_sender.send(PushTarget(sub.endpoint, sub.p256dh, sub.auth), payload)


def notify_failed_auto_approvals(
    session: Session, signals: list[Signal], environment: Environment, email_sender: EmailSender, to_email: str
) -> None:
    """A signal the pass auto-approved but never reached `executed` means its order failed —
    the kill switch already gets its own notification when it's engaged, so this only fires for
    a genuine risk/sizing rejection (story 58's "order failed" event), not a kill-switch block."""
    if killswitch.is_engaged(environment):
        return
    for signal in signals:
        if signal.status != SignalStatus.auto_approved:
            continue
        order = session.execute(
            select(Order).where(Order.idempotency_key == f"signal-{signal.id}")
        ).scalar_one_or_none()
        if order is not None and order.status == OrderStatus.failed:
            notify_order_failed(email_sender, to_email, signal, "risk/sizing check rejected the order")


def notify_kill_switch_engaged(
    email_sender: EmailSender, to_email: str, environment: Environment, engaged: bool = True
) -> None:
    send_kill_switch_email(email_sender, to_email, environment, engaged)


def notify_order_failed(email_sender: EmailSender, to_email: str, signal: Signal, reason: str) -> None:
    send_order_failed_email(email_sender, to_email, signal, reason)


def notify_daily_loss_limit(
    email_sender: EmailSender, to_email: str, environment: Environment, loss_pct: float
) -> None:
    send_daily_loss_limit_email(email_sender, to_email, environment, loss_pct)
