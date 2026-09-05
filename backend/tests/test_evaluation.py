from datetime import datetime

from loom.evaluation import compute_metrics, equity_and_benchmark_curve
from loom.market_data.base import MarketDataSource
from loom.strategy import Bar, InstrumentHistory
from loom.trade_reconstruction import ClosedTrade


def _trade(entry, exit_, qty=1.0, entry_day=1, exit_day=10):
    return ClosedTrade(
        instrument="X",
        entry_date=datetime(2024, 1, entry_day),
        exit_date=datetime(2024, 1, exit_day),
        entry_price=entry,
        exit_price=exit_,
        quantity=qty,
    )


def test_compute_metrics_with_no_trades_is_all_none():
    metrics = compute_metrics([])
    assert metrics["num_trades"] == 0
    assert metrics["win_rate"] is None
    assert metrics["rolling_sharpe"] == []


def test_compute_metrics_basic_stats():
    trades = [
        _trade(100, 110, exit_day=5),  # win
        _trade(100, 90, exit_day=10),  # loss
        _trade(100, 120, exit_day=15),  # win
        _trade(100, 95, exit_day=20),  # loss
    ]

    metrics = compute_metrics(trades)

    assert metrics["num_trades"] == 4
    assert metrics["win_rate"] == 0.5
    assert metrics["max_drawdown_pct"] is not None
    assert metrics["profit_factor"] is not None
    assert round(metrics["expectancy_pct"], 4) == round((0.10 - 0.10 + 0.20 - 0.05) / 4, 4)


def test_profit_factor_none_when_no_losses():
    trades = [_trade(100, 110, exit_day=5), _trade(100, 120, exit_day=10)]

    metrics = compute_metrics(trades)

    assert metrics["profit_factor"] is None  # no losses -> undefined ratio, not division by zero


def test_max_drawdown_reflects_a_real_dip():
    trades = [
        _trade(100, 150, exit_day=5),  # big win, pnl=50
        _trade(100, 80, exit_day=10),  # loss, pnl=-20, drawdown from peak 50 to 30
    ]

    metrics = compute_metrics(trades)

    assert round(metrics["max_drawdown_pct"], 4) == round(20 / 50, 4)


class _ScriptedBenchmarkSource(MarketDataSource):
    def __init__(self, closes: dict[str, float]):
        self.closes = closes

    def get_history(self, instrument, start, end):
        bars = tuple(Bar(date=d, open=c, high=c, low=c, close=c) for d, c in self.closes.items())
        return InstrumentHistory(instrument, bars)


def test_equity_and_benchmark_curve_aligns_by_date():
    trades = [_trade(100, 110, qty=10, entry_day=1, exit_day=10)]
    source = _ScriptedBenchmarkSource({"2024-01-01": 100.0, "2024-01-10": 105.0})

    curve = equity_and_benchmark_curve(trades, source, benchmark_instrument="VWRL.L")

    assert len(curve) == 1
    point = curve[0]
    assert point["date"] == "2024-01-10"
    assert round(point["cumulative_return_pct"], 4) == round(100 / 1000, 4)  # pnl=100 on 1000 deployed
    assert round(point["benchmark_return_pct"], 4) == 0.05


def test_equity_and_benchmark_curve_empty_when_no_trades():
    assert equity_and_benchmark_curve([], _ScriptedBenchmarkSource({})) == []
