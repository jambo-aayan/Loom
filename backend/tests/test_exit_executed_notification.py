"""Every automatically executed exit notifies (#59).

Once plan-based exits execute on their own, positions close with no interaction at all — and
before this, nothing fired on a successful automatic execution, only on a failed one. A position
closing is a fact about real money, not a request for attention.
"""

from datetime import datetime

from loom import exit_enforcement
from loom.exit_pass import run_exit_pass
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import Environment, PushSubscription
from loom.notifications.dispatch import notify_exit_executed
from loom.notifications.email import FakeEmailSender
from loom.notifications.push import FakePushSender
from tests.test_exit_pass import _PricedBroker, _held

NOON = datetime(2024, 3, 6, 12, 0)
TARGET_HIT = {"profit_target_pct": 0.05, "stop_loss_pct": 0.5, "time_exit_days": None}


def _enforce_and_run(session, price=110.0):
    exit_enforcement.enable(session, Environment.demo, actor="test")
    return run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": price}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON,
    )


def _notify(session, decisions):
    email, push = FakeEmailSender(), FakePushSender()
    notify_exit_executed(
        session,
        [d.executed_signal_id for d in decisions if d.executed_signal_id],
        Environment.demo,
        push,
        email,
        "aayan@example.com",
    )
    return email, push


def test_an_executed_exit_sends_an_email(session):
    _held(session, entry=100.0, plan=TARGET_HIT)
    email, _push = _notify(session, _enforce_and_run(session))

    assert len(email.sent) == 1
    to, subject, body = email.sent[0]
    assert to == "aayan@example.com"
    assert "TSLA" in subject
    assert "110" in body


def test_the_email_names_quantity_price_and_what_was_booked(session):
    _held(session, entry=100.0, plan=TARGET_HIT)
    email, _push = _notify(session, _enforce_and_run(session))

    body = email.sent[0][2]
    assert "10" in body          # quantity
    assert "110" in body         # exit price
    assert "Booked" in body      # realised P&L, from the FIFO reconstruction


def test_an_executed_exit_pushes_to_every_subscribed_device(session):
    _held(session, entry=100.0, plan=TARGET_HIT)
    session.add(PushSubscription(environment=Environment.demo, endpoint="e1", p256dh="p", auth="a"))
    session.commit()

    _email, push = _notify(session, _enforce_and_run(session))

    assert len(push.sent) == 1
    payload = push.sent[0][1]
    assert "TSLA" in payload["title"]
    # No action buttons: unlike a pending approval there is nothing to decide, it already happened.
    assert "actions" not in payload


def test_notification_ignores_the_notify_threshold(session):
    """Notify threshold filters proposals competing for attention. A completed exit is a fact,
    and a low-confidence position closing is exactly the case worth knowing about."""
    strategy, _config, _book = _held(session, entry=100.0, plan=TARGET_HIT)
    strategy.notify_threshold = 0.99
    session.commit()
    session.add(PushSubscription(environment=Environment.demo, endpoint="e1", p256dh="p", auth="a"))
    session.commit()

    email, push = _notify(session, _enforce_and_run(session))

    assert len(email.sent) == 1
    assert len(push.sent) == 1


def test_a_dry_run_notifies_nothing(session):
    """Nothing happened, so there is nothing to report."""
    _held(session, entry=100.0, plan=TARGET_HIT)
    decisions = run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 110.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON,
    )
    email, push = _notify(session, decisions)

    assert decisions and not email.sent and not push.sent


def test_an_exit_whose_order_never_filled_is_not_reported_as_a_sale(session):
    """Reporting a sale that did not happen would be worse than saying nothing — the order's own
    failure notification already covers it."""
    from loom.models import Order, OrderStatus

    _held(session, entry=100.0, plan=TARGET_HIT)
    decisions = _enforce_and_run(session)

    exit_order = (
        session.query(Order)
        .filter(Order.signal_id == decisions[0].executed_signal_id)
        .one()
    )
    exit_order.status = OrderStatus.failed
    session.commit()

    email, push = _notify(session, decisions)
    assert not email.sent and not push.sent
