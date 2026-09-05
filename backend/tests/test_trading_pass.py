from loom import killswitch, strategies  # noqa: F401  (registers strategies)
from loom.execution.broker import FakeBrokerClient
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import (
    ApprovalMode,
    ConfigVersionStatus,
    Environment,
    OrderStatus,
    SignalStatus,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import (
    Strategy as StrategyModel,
)
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS
from loom.trading_pass import approve_signal, execute_signal, reject_signal, run_trading_pass


def _seed_compounder(session, approval_mode=ApprovalMode.manual, approval_threshold=0.8):
    strategy = StrategyModel(
        key="low_vol_compounder",
        name="Low-Vol Compounder",
        style=StrategyStyle.trading,
        live_enabled=False,
        approval_mode=approval_mode,
        approval_threshold=approval_threshold,
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
    return strategy, config


def test_manual_approval_mode_creates_pending_signals_not_orders(session):
    _seed_compounder(session, approval_mode=ApprovalMode.manual)
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()

    signals = run_trading_pass(
        Environment.demo, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )

    assert len(signals) > 0
    assert all(s.status == SignalStatus.pending_approval for s in signals)
    assert broker.calls == []  # nothing executed yet


def test_auto_approve_mode_executes_immediately(session):
    _seed_compounder(session, approval_mode=ApprovalMode.auto)
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()

    signals = run_trading_pass(
        Environment.demo, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )

    assert len(signals) > 0
    assert all(s.status == SignalStatus.executed for s in signals)
    assert len(broker.calls) == len(signals)


def test_approve_signal_executes_via_shared_execute_path(session):
    _seed_compounder(session, approval_mode=ApprovalMode.manual)
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )
    assert signals, "fixture universe should produce at least one entry signal"
    signal = signals[0]

    order = approve_signal(session, signal, broker, note="looks good")

    assert order.status == OrderStatus.filled
    assert signal.status == SignalStatus.executed
    assert signal.note == "looks good"


def test_reject_signal_records_decision_without_ordering(session):
    _seed_compounder(session, approval_mode=ApprovalMode.manual)
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )
    signal = signals[0]

    reject_signal(session, signal, note="not convinced")

    assert signal.status == SignalStatus.rejected
    assert signal.note == "not convinced"
    assert broker.calls == []


def test_kill_switch_blocks_execution(session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    _seed_compounder(session, approval_mode=ApprovalMode.manual)
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )
    signal = signals[0]
    killswitch.engage(session, Environment.demo)

    order = approve_signal(session, signal, broker)

    assert order.status == OrderStatus.failed
    assert broker.calls == []  # blocked before ever reaching the broker


def test_execute_signal_is_idempotent_on_retry(session):
    _seed_compounder(session, approval_mode=ApprovalMode.auto)
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )
    signal = signals[0]
    calls_before_retry = len(broker.calls)

    order_again = execute_signal(session, signal, broker)

    assert len(broker.calls) == calls_before_retry  # retried execute_signal call did not resubmit
    assert order_again.status == OrderStatus.filled


def test_live_environment_skips_strategies_without_live_enabled(session):
    _seed_compounder(session, approval_mode=ApprovalMode.auto)
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()

    signals = run_trading_pass(
        Environment.live, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )

    assert signals == []
