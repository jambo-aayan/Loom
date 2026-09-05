"""Every strategy in the roster backtests end-to-end via the same path as Compounder (tickets
#32-#35 AC: "Backtest via CLI produces equity curve/stats/benchmark comparison")."""

import pytest

from loom.backtest.engine import run_backtest
from loom.market_data.fixture import FixtureMarketDataSource
from loom.strategies import ALL_STRATEGIES


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
def test_backtest_runs_end_to_end_for_every_strategy(strategy_cls):
    source = FixtureMarketDataSource()
    result = run_backtest(
        strategy=strategy_cls(),
        source=source,
        universe=source.universe(),
        start="2023-01-02",
        end="2023-12-29",
        starting_capital=10_000,
    )

    assert len(result.equity_curve) > 100
    assert "total_return_pct" in result.stats
    assert "benchmark_return_pct" in result.stats
    assert result.stats["final_equity"] > 0
