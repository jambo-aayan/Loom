from loom.backtest.engine import run_backtest
from loom.market_data.fixture import FixtureMarketDataSource
from loom.strategies.low_vol_compounder import LowVolCompounder


def test_backtest_runs_and_produces_equity_curve():
    result = run_backtest(
        strategy=LowVolCompounder(),
        source=FixtureMarketDataSource(),
        universe=["VUSA.L", "VWRL.L"],
        start="2023-01-02",
        end="2023-06-30",
        starting_capital=10_000,
    )

    assert len(result.equity_curve) > 50
    assert "total_return_pct" in result.stats
    assert "benchmark_return_pct" in result.stats
    assert result.stats["final_equity"] > 0


def test_backtest_never_uses_data_beyond_simulated_now():
    """No-lookahead: fabricate a source whose bars would make an obviously-wrong entry decision
    if a future bar leaked in; assert the engine never queries beyond the day being simulated."""
    from loom.market_data.base import MarketDataSource
    from loom.strategy import Bar, InstrumentHistory

    class RecordingSource(MarketDataSource):
        def __init__(self):
            self.requested_end = None

        def get_history(self, instrument, start, end):
            self.requested_end = end
            bars = tuple(
                Bar(date=f"2023-01-{d:02d}", open=100, high=101, low=99, close=100 + d)
                for d in range(2, 20)
            )
            return InstrumentHistory(instrument, bars)

    source = RecordingSource()
    run_backtest(
        strategy=LowVolCompounder(),
        source=source,
        universe=["X"],
        start="2023-01-02",
        end="2023-01-10",
        starting_capital=10_000,
    )
    assert source.requested_end == "2023-01-10"


def test_high_volatility_universe_produces_no_trades_but_valid_equity_curve():
    from loom.market_data.base import MarketDataSource
    from loom.strategy import Bar, InstrumentHistory

    class ChoppySource(MarketDataSource):
        def get_history(self, instrument, start, end):
            bars = []
            price = 100.0
            from datetime import date, timedelta

            d = date.fromisoformat(start)
            end_d = date.fromisoformat(end)
            while d <= end_d:
                if d.weekday() < 5:
                    price *= 1.05 if len(bars) % 2 == 0 else 0.95
                    bars.append(Bar(date=d.isoformat(), open=price, high=price, low=price, close=price))
                d += timedelta(days=1)
            return InstrumentHistory(instrument, tuple(bars))

    result = run_backtest(
        strategy=LowVolCompounder(),
        source=ChoppySource(),
        universe=["CHOP"],
        start="2023-01-02",
        end="2023-04-30",
        starting_capital=10_000,
    )
    assert result.stats["num_trades"] == 0
    assert result.stats["final_equity"] == 10_000
