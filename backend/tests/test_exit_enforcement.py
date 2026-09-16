"""Live exit enforcement (#58, ADR-0018): plan-based exits execute without approval.

ADR-0009 already held that an exit realising a pre-calculated level is arithmetic rather than a
forecast — the code simply never acted on it, so under the default `manual` mode a stop-loss
queued for a click. A stop that waits for a click is not a stop.
"""

from datetime import datetime

from loom import auto_trading_gate, exit_enforcement, killswitch
from loom.exit_pass import run_exit_pass
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import (
    ApprovalMode,
    Environment,
    ExitObservation,
    Order,
    OrderStatus,
    Signal,
    SignalStatus,
    SignalType,
)
from loom.trading_pass import book_positions
from tests.test_exit_pass import _PricedBroker, _held

NOON = datetime(2024, 3, 6, 12, 0)
TARGET_HIT = {"profit_target_pct": 0.05, "stop_loss_pct": 0.5, "time_exit_days": None}


def _run(session, price=110.0):
    return run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": price}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON,
    )


def test_enforcement_is_off_by_default(session):
    assert exit_enforcement.is_enforcing(session, Environment.demo) is False


def test_a_plan_based_exit_executes_without_approval_under_manual_mode(session):
    """The default Approval mode is `manual` for every strategy. A plan-based exit ignores it."""
    strategy, _config, book = _held(session, entry=100.0, plan=TARGET_HIT)
    strategy.approval_mode = ApprovalMode.manual
    session.commit()
    exit_enforcement.enable(session, Environment.demo, actor="test")

    _run(session)

    exit_signal = session.query(Signal).filter(Signal.signal_type == SignalType.exit).one()
    assert exit_signal.status in (SignalStatus.auto_approved, SignalStatus.executed)
    assert exit_signal.requires_manual_approval is False
    assert session.query(Order).filter(Order.status == OrderStatus.filled).count() == 2  # buy + sell
    assert book_positions(session, book.id) == ()


def test_the_auto_trading_gate_does_not_hold_back_a_plan_based_exit(session):
    """A circuit breaker that stopped you closing a losing position would be the wrong shape, so
    the gate governs entries and discretionary exits only (CONTEXT.md)."""
    _held(session, entry=100.0, plan=TARGET_HIT)
    auto_trading_gate.disable(session, actor="test")
    exit_enforcement.enable(session, Environment.demo, actor="test")

    _run(session)

    exit_signal = session.query(Signal).filter(Signal.signal_type == SignalType.exit).one()
    assert exit_signal.status in (SignalStatus.auto_approved, SignalStatus.executed)


def test_the_kill_switch_still_blocks_everything(session):
    """Unconditional by design, even though the daily-loss limit auto-engages it — an emergency is
    the worst moment to have to recall which half still fires (ADR-0018)."""
    _held(session, entry=100.0, plan=TARGET_HIT)
    exit_enforcement.enable(session, Environment.demo, actor="test")
    killswitch.engage(session, Environment.demo, actor="test")

    assert _run(session) == []
    assert session.query(Signal).filter(Signal.signal_type == SignalType.exit).count() == 0
    assert session.query(ExitObservation).count() == 0


def test_an_exit_is_attributed_to_the_strategy_that_owns_the_book(session):
    """Per-Strategy performance must still account for every trade."""
    strategy, config, _book = _held(session, entry=100.0, plan=TARGET_HIT)
    exit_enforcement.enable(session, Environment.demo, actor="test")

    _run(session)

    exit_signal = session.query(Signal).filter(Signal.signal_type == SignalType.exit).one()
    assert exit_signal.strategy_id == strategy.id
    assert exit_signal.config_version_id == config.id


def test_enforcing_writes_no_dry_run_observations(session):
    """The two modes are exclusive: once acting, the audit table stops accumulating."""
    _held(session, entry=100.0, plan=TARGET_HIT)
    exit_enforcement.enable(session, Environment.demo, actor="test")

    _run(session)

    assert session.query(ExitObservation).count() == 0


def test_positions_opened_before_enforcement_existed_are_governed(session):
    """Those are precisely the positions that have no exit today — grandfathering them means they
    keep having none."""
    _held(session, entry=100.0, plan=TARGET_HIT)  # opened while nothing enforced
    exit_enforcement.enable(session, Environment.demo, actor="test")

    assert len(_run(session)) == 1


def test_disabling_returns_to_observing(session):
    _held(session, entry=100.0, plan=TARGET_HIT)
    exit_enforcement.enable(session, Environment.demo, actor="test")
    exit_enforcement.disable(session, Environment.demo, actor="test")

    _run(session)

    assert session.query(Signal).filter(Signal.signal_type == SignalType.exit).count() == 0
    assert session.query(ExitObservation).count() == 1


def test_enforcement_is_scoped_per_environment(session):
    exit_enforcement.enable(session, Environment.live, actor="test")
    assert exit_enforcement.is_enforcing(session, Environment.demo) is False
    assert exit_enforcement.is_enforcing(session, Environment.live) is True
