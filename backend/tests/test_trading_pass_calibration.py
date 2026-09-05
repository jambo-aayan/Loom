"""Ticket #36 AC: "A live entry-type signal's confidence is looked up from the bucket its
strength falls into, replacing any placeholder/hand-tuned value" — and exit-type signals stay
unaffected."""

from sqlalchemy import select

from loom import calibration, strategies  # noqa: F401
from loom.execution.broker import FakeBrokerClient
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import (
    ApprovalMode,
    ConfidenceCalibration,
    ConfigVersionStatus,
    Environment,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import Strategy as StrategyModel
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS
from loom.trading_pass import run_trading_pass


def _force_single_bucket(session, win_rate: float) -> None:
    """Overwrites whatever save_calibration computed with one wide bucket covering any plausible
    strength, so the resulting confidence is a known, deliberately-unlikely-to-collide value —
    proof the calibration path fired, not a coincidence with the strategy's own placeholder."""
    calib_row = session.execute(select(ConfidenceCalibration)).scalars().first()
    calib_row.buckets = [{"min": -100.0, "max": 100.0, "win_rate": win_rate, "expectancy": 0.0, "num_trades": 10}]
    session.commit()


def _seed(session):
    strategy = StrategyModel(
        key="low_vol_compounder",
        name="Low-Vol Compounder",
        style=StrategyStyle.trading,
        approval_mode=ApprovalMode.manual,
    )
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params=dict(DEFAULT_PARAMS)
    )
    session.add(config)
    session.commit()
    return strategy, config


def test_entry_signal_confidence_is_overridden_by_calibration(session):
    strategy, config = _seed(session)
    source = FixtureMarketDataSource()

    calibration.save_calibration(session, strategy.id, config.id, trades=[])
    _force_single_bucket(session, win_rate=0.13)

    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )

    entries = [s for s in signals if s.signal_type == "entry"]
    assert entries, "fixture universe should produce at least one entry signal"
    for signal in entries:
        assert signal.confidence == 0.13


def test_exit_signal_confidence_is_unaffected_by_calibration(session):
    strategy, config = _seed(session)
    source = FixtureMarketDataSource()
    calibration.save_calibration(session, strategy.id, config.id, trades=[])
    _force_single_bucket(session, win_rate=0.13)

    # Force an exit by seeding a held position that's already comfortably past the profit target.
    from loom.models import Order, OrderStatus, Signal, SignalStatus, SignalType
    from loom.trading_pass import get_or_create_book

    book = get_or_create_book(session, strategy.id, Environment.demo, "Compounder · demo")
    seed_signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument="VUSA.L",
        signal_type=SignalType.entry,
        action="buy",
        confidence=0.8,
        exit_plan={"profit_target_pct": None, "stop_loss_pct": None, "time_exit_days": None},
        quantity=10,
        reference_price=1.0,  # comfortably below any real fixture close -> guaranteed profit exit
        status=SignalStatus.executed,
    )
    session.add(seed_signal)
    session.flush()
    session.add(
        Order(
            signal_id=seed_signal.id,
            book_id=book.id,
            environment=Environment.demo,
            idempotency_key="seed-order",
            status=OrderStatus.filled,
            quantity=10,
            fill_price=1.0,
        )
    )
    session.commit()

    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )

    exits = [s for s in signals if s.signal_type == "exit"]
    assert exits, "expected the seeded winning position to trigger an exit"
    for signal in exits:
        assert signal.confidence != 0.13
        assert signal.confidence >= 0.9
