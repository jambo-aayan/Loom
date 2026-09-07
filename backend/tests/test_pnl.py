from datetime import date

from loom.market_data.base import MarketDataSource
from loom.models import Book, Environment
from loom.pnl import book_pnl
from loom.strategy import Bar, InstrumentHistory, PositionSnapshot


class _StubSource(MarketDataSource):
    def __init__(self, latest_close: float):
        self.latest_close = latest_close

    def get_history(self, instrument, start, end):
        return InstrumentHistory(
            instrument=instrument,
            bars=(Bar(date=date.today().isoformat(), open=0, high=0, low=0, close=self.latest_close, volume=0),),
        )


class _EmptySource(MarketDataSource):
    def get_history(self, instrument, start, end):
        return InstrumentHistory(instrument=instrument, bars=())


def _book(strategy_id="strat-1"):
    return Book(id="book-1", strategy_id=strategy_id, environment=Environment.demo, name="Compounder · demo")


def test_book_pnl_computes_market_value_and_unrealized_gain():
    positions = (PositionSnapshot(instrument="VUSA.L", quantity=10, average_price=100.0, book_id="book-1"),)
    source = _StubSource(latest_close=110.0)

    pnl = book_pnl(_book(), positions, source)

    assert pnl is not None
    assert pnl.cost_basis == 1000.0
    assert pnl.market_value == 1100.0
    assert pnl.unrealized_pnl == 100.0
    assert round(pnl.unrealized_pnl_pct, 4) == 0.1


def test_book_pnl_handles_an_unrealized_loss():
    positions = (PositionSnapshot(instrument="VUSA.L", quantity=10, average_price=100.0, book_id="book-1"),)
    source = _StubSource(latest_close=90.0)

    pnl = book_pnl(_book(), positions, source)

    assert pnl.unrealized_pnl == -100.0
    assert round(pnl.unrealized_pnl_pct, 4) == -0.1


def test_book_pnl_returns_none_for_a_book_with_no_positions():
    pnl = book_pnl(_book(), (), _StubSource(latest_close=100.0))

    assert pnl is None


def test_book_pnl_falls_back_to_cost_basis_when_no_price_history():
    positions = (PositionSnapshot(instrument="UNKNOWN", quantity=5, average_price=50.0, book_id="book-1"),)

    pnl = book_pnl(_book(), positions, _EmptySource())

    assert pnl.market_value == 250.0
    assert pnl.unrealized_pnl == 0.0


def test_book_pnl_sums_multiple_positions():
    positions = (
        PositionSnapshot(instrument="VUSA.L", quantity=10, average_price=100.0, book_id="book-1"),
        PositionSnapshot(instrument="VWRL.L", quantity=5, average_price=200.0, book_id="book-1"),
    )
    source = _StubSource(latest_close=120.0)

    pnl = book_pnl(_book(), positions, source)

    assert pnl.cost_basis == 1000.0 + 1000.0
    assert pnl.market_value == 1200.0 + 600.0


def test_book_pnl_manual_book_has_no_strategy_key():
    positions = (PositionSnapshot(instrument="AAPL", quantity=1, average_price=150.0, book_id="book-1"),)
    manual_book = Book(id="book-1", strategy_id=None, environment=Environment.demo, name="Manual")

    pnl = book_pnl(manual_book, positions, _StubSource(latest_close=150.0))

    assert pnl.strategy_key is None
    assert pnl.book_name == "Manual"
