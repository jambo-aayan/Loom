from datetime import datetime

from tests.test_trade_reconstruction import _fill, _seed_book
from loom.models import Strategy as StrategyModel


def test_booked_trade_none_for_a_buy_signal(session):
    _, config, book = _seed_book(session)
    strategy = session.get(StrategyModel, book.strategy_id)
    signal = _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))

    assert signal.booked_trade is None


def test_booked_trade_reflects_the_gain_on_a_simple_sell(session):
    _, config, book = _seed_book(session)
    strategy = session.get(StrategyModel, book.strategy_id)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    sell_signal = _fill(session, strategy, config, book, "sell", 110.0, 10, datetime(2024, 1, 10))

    booked = sell_signal.booked_trade

    assert booked is not None
    assert booked.instrument == "VUSA.L"
    assert booked.quantity == 10
    assert booked.realized_pnl == 100.0
    assert round(booked.realized_pnl_pct, 4) == 0.1


def test_booked_trade_aggregates_a_sell_that_closes_two_lots(session):
    _, config, book = _seed_book(session)
    strategy = session.get(StrategyModel, book.strategy_id)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "buy", 120.0, 5, datetime(2024, 1, 5))
    sell_signal = _fill(session, strategy, config, book, "sell", 130.0, 12, datetime(2024, 1, 20))

    booked = sell_signal.booked_trade

    # (130-100)*10 + (130-120)*2 = 300 + 20 = 320
    assert booked.quantity == 12
    assert booked.realized_pnl == 320.0
