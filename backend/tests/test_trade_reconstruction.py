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
from loom.trade_reconstruction import reconstruct_closed_trades


def _seed_book(session):
    strategy = StrategyModel(
        key="low_vol_compounder",
        name="Low-Vol Compounder",
        style=StrategyStyle.trading,
        approval_mode=ApprovalMode.auto,
    )
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params={}
    )
    book = Book(strategy_id=strategy.id, environment=Environment.demo, name="Compounder · demo")
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
        instrument="VUSA.L",
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
    order = Order(
        signal_id=signal.id,
        book_id=book.id,
        environment=Environment.demo,
        idempotency_key=f"idem-{signal.id}",
        status=OrderStatus.filled,
        quantity=quantity,
        fill_price=price,
        filled_at=at,
    )
    session.add(order)
    session.commit()


def test_simple_buy_then_sell_closes_one_trade(session):
    _, config, book = _seed_book(session)
    strategy = session.get(StrategyModel, book.strategy_id)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "sell", 110.0, 10, datetime(2024, 1, 10))

    trades = reconstruct_closed_trades(session, book.id)

    assert len(trades) == 1
    assert trades[0].pnl == 100.0
    assert round(trades[0].return_pct, 4) == 0.1
    assert trades[0].hold_days == 9


def test_fifo_matches_oldest_lot_first_and_can_split_a_lot(session):
    _, config, book = _seed_book(session)
    strategy = session.get(StrategyModel, book.strategy_id)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "buy", 120.0, 5, datetime(2024, 1, 5))
    _fill(session, strategy, config, book, "sell", 130.0, 12, datetime(2024, 1, 20))

    trades = reconstruct_closed_trades(session, book.id)

    assert len(trades) == 2
    assert trades[0].entry_price == 100.0 and trades[0].quantity == 10
    assert trades[1].entry_price == 120.0 and trades[1].quantity == 2


def test_open_position_produces_no_closed_trades(session):
    _, config, book = _seed_book(session)
    strategy = session.get(StrategyModel, book.strategy_id)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))

    trades = reconstruct_closed_trades(session, book.id)

    assert trades == []
