from datetime import datetime, timedelta

import pytest

from loom.models import (
    ApprovalMode,
    Book,
    ConfigVersionStatus,
    Environment,
    Signal,
    SignalStatus,
    SignalType,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import (
    Strategy as StrategyModel,
)
from loom.notifications.email import (
    ActionLinkError,
    FakeEmailSender,
    consume_action_link,
    generate_action_link,
    send_pending_approval_email,
)


def _seed_signal(session):
    strategy = StrategyModel(
        key="low_vol_compounder",
        name="Low-Vol Compounder",
        style=StrategyStyle.trading,
        approval_mode=ApprovalMode.manual,
    )
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params={}
    )
    book = Book(strategy_id=strategy.id, environment=Environment.demo, name="Compounder · demo")
    session.add_all([config, book])
    session.flush()
    signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument="VUSA.L",
        signal_type=SignalType.entry,
        action="buy",
        confidence=0.9,
        exit_plan={"profit_target_pct": None, "stop_loss_pct": None, "time_exit_days": None},
        quantity=10,
        reference_price=100.0,
        status=SignalStatus.pending_approval,
    )
    session.add(signal)
    session.commit()
    return signal


def test_generate_and_consume_action_link(session):
    signal = _seed_signal(session)

    url = generate_action_link(session, signal.id, "approve")
    token = url.rsplit("/", 1)[-1]

    link = consume_action_link(session, token)

    assert link.signal_id == signal.id
    assert link.action == "approve"
    assert link.used_at is not None


def test_consuming_a_link_twice_raises(session):
    signal = _seed_signal(session)
    url = generate_action_link(session, signal.id, "reject")
    token = url.rsplit("/", 1)[-1]
    consume_action_link(session, token)

    with pytest.raises(ActionLinkError):
        consume_action_link(session, token)


def test_expired_link_raises(session):
    signal = _seed_signal(session)
    url = generate_action_link(session, signal.id, "approve", ttl_hours=1)
    token = url.rsplit("/", 1)[-1]

    from sqlalchemy import select

    from loom.models import SignedActionLink

    link = session.execute(select(SignedActionLink).where(SignedActionLink.token == token)).scalar_one()
    link.expires_at = datetime.utcnow() - timedelta(hours=1)
    session.commit()

    with pytest.raises(ActionLinkError):
        consume_action_link(session, token)


def test_unknown_token_raises(session):
    with pytest.raises(ActionLinkError):
        consume_action_link(session, "not-a-real-token")


def test_pending_approval_email_contains_both_action_links(session):
    signal = _seed_signal(session)
    sender = FakeEmailSender()

    send_pending_approval_email(session, sender, "user@example.com", signal)

    assert len(sender.sent) == 1
    to, subject, body = sender.sent[0]
    assert to == "user@example.com"
    assert "action-links" in body
    assert body.count("action-links") == 2  # one approve link, one reject link
