"""Exit `Signal` lifecycle (#52).

An entry expires because the opportunity genuinely passes — the price moved on. An exit's reason
does not: the trend ended and you are still holding. Expiring it discards the strategy's judgment
and silently defaults to "hold", the one outcome nobody chose.
"""

from datetime import datetime, timedelta

from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import Environment, Signal, SignalStatus, SignalType
from loom.trading_pass import expire_stale_signals
from tests.test_book_positions_add_count import _fill, _seed_book

LONG_AGO = datetime.utcnow() - timedelta(hours=72)


def _pending(session, strategy, config, book, signal_type, action, instrument="TSLA"):
    signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument=instrument,
        signal_type=signal_type,
        action=action,
        confidence=0.9,
        exit_plan={"profit_target_pct": 0.05, "stop_loss_pct": 0.03, "time_exit_days": 30},
        quantity=1.0,
        reference_price=100.0,
        status=SignalStatus.pending_approval,
        created_at=LONG_AGO,
    )
    session.add(signal)
    session.commit()
    return signal


def test_an_exit_is_not_expired_while_its_position_is_open(session):
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    exit_signal = _pending(session, strategy, config, book, SignalType.exit, "sell")

    expire_stale_signals(session, Environment.demo, FixtureMarketDataSource())

    session.refresh(exit_signal)
    assert exit_signal.status == SignalStatus.pending_approval
    assert exit_signal.counterfactual_outcome is None


def test_an_exit_is_withdrawn_once_its_position_has_closed(session):
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "sell", 105.0, 10, datetime(2024, 1, 9))
    exit_signal = _pending(session, strategy, config, book, SignalType.exit, "sell")

    expire_stale_signals(session, Environment.demo, FixtureMarketDataSource())

    session.refresh(exit_signal)
    assert exit_signal.status == SignalStatus.withdrawn
    assert exit_signal.decided_at is not None


def test_a_withdrawn_exit_carries_no_counterfactual(session):
    """A counterfactual answers "what would have happened had you acted on this". For an exit
    whose position is already gone there is nothing to simulate and no judgment to evaluate."""
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "sell", 105.0, 10, datetime(2024, 1, 9))
    exit_signal = _pending(session, strategy, config, book, SignalType.exit, "sell")

    expire_stale_signals(session, Environment.demo, FixtureMarketDataSource())

    session.refresh(exit_signal)
    assert exit_signal.counterfactual_outcome is None


def test_a_withdrawn_exit_is_distinguishable_from_a_rejection(session):
    """History must not read a withdrawal as a decision the user made — they made none."""
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "sell", 105.0, 10, datetime(2024, 1, 9))
    exit_signal = _pending(session, strategy, config, book, SignalType.exit, "sell")

    expire_stale_signals(session, Environment.demo, FixtureMarketDataSource())

    session.refresh(exit_signal)
    assert exit_signal.status not in (SignalStatus.rejected, SignalStatus.expired)
    assert exit_signal.note is None


def test_entry_signals_still_expire(session):
    strategy, config, book = _seed_book(session)
    entry = _pending(session, strategy, config, book, SignalType.entry, "buy", instrument="VUSA.L")

    expired = expire_stale_signals(session, Environment.demo, FixtureMarketDataSource())

    session.refresh(entry)
    assert entry.status == SignalStatus.expired
    assert entry.counterfactual_outcome is not None
    assert entry.id in [s.id for s in expired]
