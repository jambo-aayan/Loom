from datetime import datetime

from loom.models import (
    ApprovalMode,
    Book,
    ConfigVersionStatus,
    Environment,
    Order,
    OrderStatus,
    Signal,
    SignalStatus,
    SignalType,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import (
    Strategy as StrategyModel,
)
from loom.trading_pass import book_positions


def _seed_book(session):
    strategy = StrategyModel(
        key="volatility_harvester",
        name="Volatility Harvester",
        style=StrategyStyle.trading,
        approval_mode=ApprovalMode.auto,
    )
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params={}
    )
    book = Book(strategy_id=strategy.id, environment=Environment.demo, name="Harvester · demo")
    session.add_all([config, book])
    session.flush()
    session.commit()
    return strategy, config, book


def _fill(session, strategy, config, book, action, price, quantity, at):
    signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument="TSLA",
        signal_type=SignalType.entry if action != "sell" else SignalType.exit,
        action=action,
        confidence=0.9,
        exit_plan={"profit_target_pct": None, "stop_loss_pct": None, "time_exit_days": None},
        quantity=quantity,
        reference_price=price,
        status=SignalStatus.executed,
    )
    session.add(signal)
    session.flush()
    session.add(
        Order(
            signal_id=signal.id,
            book_id=book.id,
            environment=Environment.demo,
            idempotency_key=f"idem-{signal.id}",
            status=OrderStatus.filled,
            quantity=quantity,
            fill_price=price,
            filled_at=at,
        )
    )
    session.commit()


def test_opening_buy_has_add_count_one(session):
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))

    positions = book_positions(session, book.id)

    assert len(positions) == 1
    assert positions[0].add_count == 1


def test_each_add_increments_add_count(session):
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "add", 90.0, 5, datetime(2024, 1, 5))
    _fill(session, strategy, config, book, "add", 80.0, 5, datetime(2024, 1, 10))

    positions = book_positions(session, book.id)

    assert positions[0].add_count == 3


def test_add_count_resets_after_a_full_exit_and_fresh_buy(session):
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "add", 90.0, 5, datetime(2024, 1, 5))
    _fill(session, strategy, config, book, "sell", 95.0, 15, datetime(2024, 1, 10))
    _fill(session, strategy, config, book, "buy", 110.0, 8, datetime(2024, 1, 20))

    positions = book_positions(session, book.id)

    assert len(positions) == 1
    assert positions[0].add_count == 1
