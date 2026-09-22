from loom import auto_trading_gate, killswitch, live_trading_gate, strategies  # noqa: F401  (registers strategies)
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


def test_live_trading_gate_off_blocks_a_live_pass_even_with_live_enabled_strategy(session):
    live_trading_gate.disable(session)
    strategy, _ = _seed_compounder(session, approval_mode=ApprovalMode.auto)
    strategy.live_enabled = True
    session.commit()
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()

    signals = run_trading_pass(
        Environment.live, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )

    assert signals == []
    assert broker.calls == []


def test_live_trading_gate_off_blocks_manual_approval_of_an_already_pending_live_signal(session):
    strategy, config = _seed_compounder(session, approval_mode=ApprovalMode.manual)
    strategy.live_enabled = True
    session.commit()
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.live, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )
    assert signals, "fixture universe should produce at least one entry signal"
    signal = signals[0]

    live_trading_gate.disable(session)
    order = approve_signal(session, signal, broker)

    assert order.status == OrderStatus.failed
    assert broker.calls == []  # blocked before ever reaching the broker


def test_auto_trading_gate_off_forces_manual_approval_regardless_of_strategy_mode(session):
    auto_trading_gate.disable(session)
    strategy, _ = _seed_compounder(session, approval_mode=ApprovalMode.auto)

    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, broker, source, universe=source.universe(), as_of="2023-08-01"
    )

    assert len(signals) > 0
    assert all(s.status == SignalStatus.pending_approval for s in signals)
    assert broker.calls == []
    # the strategy's own configured approval_mode is untouched — a non-destructive circuit breaker
    assert strategy.approval_mode == ApprovalMode.auto


class _StaleFixtureSource(FixtureMarketDataSource):
    """Fixture bars, but instruments in `stale` fail the freshness check and those in `down` fail
    to fetch at all."""

    def __init__(self, stale=(), down=()):
        super().__init__()
        self.stale, self.down = set(stale), set(down)

    def get_history(self, instrument, start, end):
        if instrument in self.down:
            raise RuntimeError("provider down")
        return super().get_history(instrument, start, end)

    def check_fresh(self, history):
        from loom.market_data.freshness import StaleDataError

        if history.instrument in self.stale:
            raise StaleDataError(f"{history.instrument}: stale")


def test_stale_market_data_blocks_entries(session):
    # Decision D25: no fresh data -> no entries for that instrument in that scan.
    _seed_compounder(session, approval_mode=ApprovalMode.manual)
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    universe = FixtureMarketDataSource().universe()

    stale = _StaleFixtureSource(stale=universe)
    signals = run_trading_pass(Environment.demo, session, broker, stale, universe=universe, as_of="2023-08-01")
    assert [s for s in signals if s.signal_type == "entry"] == []

    # The same pass on fresh data does produce entries, so the block above is the freshness check.
    fresh = run_trading_pass(
        Environment.demo, session, broker, FixtureMarketDataSource(), universe=universe, as_of="2023-08-01"
    )
    assert [s for s in fresh if s.signal_type == "entry"]


def test_one_instruments_data_failure_does_not_stop_the_pass(session):
    _seed_compounder(session, approval_mode=ApprovalMode.manual)
    broker = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    universe = FixtureMarketDataSource().universe()

    first = run_trading_pass(
        Environment.demo, session, broker, _StaleFixtureSource(down={"VUSA.L"}), universe=universe, as_of="2023-08-01"
    )
    assert first, "the other instruments still produce signals"
    assert "VUSA.L" not in {s.instrument for s in first}

    # Once its data is back, VUSA.L gets its signal (the others are already pending, so not repeated).
    second = run_trading_pass(
        Environment.demo, session, broker, FixtureMarketDataSource(), universe=universe, as_of="2023-08-01"
    )
    assert {s.instrument for s in second} == {"VUSA.L"}
