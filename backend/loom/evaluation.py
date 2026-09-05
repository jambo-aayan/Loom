"""Evaluation metrics beyond raw return (story 70, ticket #37): max drawdown, win rate, profit
factor, expectancy per trade, and rolling Sharpe/Sortino, computed from real closed trades
(`loom.trade_reconstruction`) — per `Book` and in aggregate — plus every chart plotted against a
benchmark over the same period (story 71).

**Known v1 simplification**: Sharpe/Sortino here are computed from the *per-trade* return series
(not a daily NAV series — there isn't one; trades are event-driven, not marked to market daily),
annualized by the average holding period. This is a standard practical approximation for
trade-level series, not a full daily-returns Sharpe — worth revisiting if a daily equity curve
becomes worth building for its own sake.
"""

from __future__ import annotations

import math
import statistics

from loom.market_data.base import MarketDataSource
from loom.trade_reconstruction import ClosedTrade

DEFAULT_BENCHMARK_INSTRUMENT = "VWRL.L"  # a global tracker, per story 71's own example
TRADING_DAYS_PER_YEAR = 252


def compute_metrics(trades: list[ClosedTrade], rolling_window: int = 5) -> dict:
    if not trades:
        return {
            "num_trades": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy_pct": None,
            "max_drawdown_pct": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "rolling_sharpe": [],
        }

    ordered = sorted(trades, key=lambda t: t.exit_date)
    returns = [t.return_pct for t in ordered]
    pnls = [t.pnl for t in ordered]

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    avg_hold_days = statistics.fmean(t.hold_days for t in ordered) or 1
    periods_per_year = TRADING_DAYS_PER_YEAR / avg_hold_days

    sharpe = _sharpe(returns, periods_per_year)
    sortino = _sortino(returns, periods_per_year)
    rolling = _rolling_sharpe(returns, rolling_window, periods_per_year)

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnls:
        cumulative += pnl
        peak = max(peak, cumulative)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - cumulative) / peak)

    return {
        "num_trades": len(ordered),
        "win_rate": len(wins) / len(ordered),
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "expectancy_pct": statistics.fmean(returns),
        "max_drawdown_pct": max_drawdown,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "rolling_sharpe": rolling,
    }


def _sharpe(returns: list[float], periods_per_year: float) -> float | None:
    if len(returns) < 2:
        return None
    mean, stdev = statistics.fmean(returns), statistics.pstdev(returns)
    if stdev == 0:
        return None
    return (mean / stdev) * math.sqrt(periods_per_year)


def _sortino(returns: list[float], periods_per_year: float) -> float | None:
    downside = [r for r in returns if r < 0]
    if len(returns) < 2 or not downside:
        return None
    downside_dev = statistics.pstdev(downside)
    if downside_dev == 0:
        return None
    return (statistics.fmean(returns) / downside_dev) * math.sqrt(periods_per_year)


def _rolling_sharpe(returns: list[float], window: int, periods_per_year: float) -> list[float | None]:
    return [
        _sharpe(returns[max(0, i - window + 1) : i + 1], periods_per_year) if i + 1 >= min(window, 2) else None
        for i in range(len(returns))
    ]


def equity_and_benchmark_curve(
    trades: list[ClosedTrade],
    source: MarketDataSource,
    benchmark_instrument: str = DEFAULT_BENCHMARK_INSTRUMENT,
) -> list[dict]:
    """A point per closed trade's exit date: cumulative realized P&L (as a % of the total
    capital deployed across trades so it's comparable to the benchmark's % return) alongside the
    benchmark instrument's cumulative return over the same period (story 71)."""
    if not trades:
        return []
    ordered = sorted(trades, key=lambda t: t.exit_date)
    start_date = min(t.entry_date for t in ordered).date().isoformat()
    end_date = ordered[-1].exit_date.date().isoformat()

    benchmark_history = source.get_history(benchmark_instrument, start_date, end_date)
    benchmark_by_date = {bar.date: bar.close for bar in benchmark_history.bars}
    benchmark_start = benchmark_history.bars[0].close if benchmark_history.bars else None

    capital_base = sum(t.entry_price * t.quantity for t in ordered) or 1.0
    cumulative_pnl = 0.0
    curve = []
    last_benchmark_close = benchmark_start
    for trade in ordered:
        cumulative_pnl += trade.pnl
        exit_date_str = trade.exit_date.date().isoformat()
        if exit_date_str in benchmark_by_date:
            last_benchmark_close = benchmark_by_date[exit_date_str]
        benchmark_return = (
            (last_benchmark_close - benchmark_start) / benchmark_start
            if benchmark_start and last_benchmark_close is not None
            else None
        )
        curve.append(
            {
                "date": exit_date_str,
                "cumulative_return_pct": cumulative_pnl / capital_base,
                "benchmark_return_pct": benchmark_return,
            }
        )
    return curve
