from loom import strategies  # noqa: F401
from loom.execution.broker import FakeBrokerClient
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import (
    ApprovalMode,
    ConfigVersionStatus,
    Environment,
    PushSubscription,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import (
    Strategy as StrategyModel,
)
from loom.notifications.dispatch import notify_failed_auto_approvals, notify_new_signals
from loom.notifications.email import FakeEmailSender
from loom.notifications.push import FakePushSender
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS
from loom.trading_pass import run_trading_pass


def _seed(session, approval_mode=ApprovalMode.manual, notify_threshold=0.0):
    strategy = StrategyModel(
        key="low_vol_compounder",
        name="Low-Vol Compounder",
        style=StrategyStyle.trading,
        approval_mode=approval_mode,
        notify_threshold=notify_threshold,
    )
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id,
        version_number=1,
        status=ConfigVersionStatus.promoted,
        params=dict(DEFAULT_PARAMS),
    )
    session.add(config)
    session.commit()
    return strategy


def test_pending_signals_always_get_an_email(session):
    _seed(session, approval_mode=ApprovalMode.manual, notify_threshold=1.1)  # unreachable -> no push
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )
    email_sender, push_sender = FakeEmailSender(), FakePushSender()

    notify_new_signals(session, signals, push_sender, email_sender, "user@example.com")

    assert len(email_sender.sent) == len(signals)
    assert push_sender.sent == []  # threshold unreachable, no push should fire


def test_push_only_fires_above_notify_threshold(session):
    _seed(session, approval_mode=ApprovalMode.manual, notify_threshold=0.0)  # everything clears it
    session.add(
        PushSubscription(environment=Environment.demo, endpoint="https://push.example/1", p256dh="k", auth="a")
    )
    session.commit()
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )
    email_sender, push_sender = FakeEmailSender(), FakePushSender()

    notify_new_signals(session, signals, push_sender, email_sender, "user@example.com")

    assert len(push_sender.sent) == len(signals)


def test_notify_failed_auto_approvals_skips_when_kill_switch_engaged(session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom import killswitch

    _seed(session, approval_mode=ApprovalMode.auto)
    source = FixtureMarketDataSource()
    killswitch.engage(session, Environment.demo)
    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )
    email_sender = FakeEmailSender()

    notify_failed_auto_approvals(session, signals, Environment.demo, email_sender, "user@example.com")

    assert email_sender.sent == []  # the kill switch already "explains" the failure
