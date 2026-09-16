"""Counterfactual outcome tracking (story 67, CONTEXT.md "Counterfactual outcome"): a rejected
or expired Signal keeps being simulated forward as a shadow position, reusing the backtest
engine's own fill/exit logic, until it resolves or hits a max horizon.

Simulates the Signal's own `ExitPlan` (via the shared `check_exit`) and nothing else — the
originating Strategy is never re-run, so a discretionary exit it would have taken (a death cross,
a volatility normalisation) is not reflected here. For the three strategies whose exits are purely
plan-based this is exact; for Trend Follower and Volatility Breakout it is an approximation.
Deliberate, per ADR-0018: full fidelity would mean re-running a strategy forward per rejected
signal on every refresh, to improve two strategies out of five."""

from __future__ import annotations

from datetime import date, timedelta

from loom.backtest.engine import ExitPlan, TradeRecord, check_trade_exit
from loom.market_data.base import MarketDataSource

DEFAULT_MAX_HORIZON_DAYS = 90


def simulate_counterfactual(
    instrument: str,
    entry_date: str,
    entry_price: float,
    exit_plan: ExitPlan,
    source: MarketDataSource,
    max_horizon_days: int = DEFAULT_MAX_HORIZON_DAYS,
    as_of: date | None = None,
) -> dict:
    start_d = date.fromisoformat(entry_date)
    horizon_end = start_d + timedelta(days=max_horizon_days)
    as_of = as_of or horizon_end
    fetch_end = min(horizon_end, as_of)

    history = source.get_history(instrument, entry_date, fetch_end.isoformat())
    trade = TradeRecord(
        instrument=instrument,
        entry_date=entry_date,
        entry_price=entry_price,
        quantity=1.0,
        exit_plan=exit_plan,
    )

    last_close = entry_price
    for bar in history.bars:
        if bar.date == entry_date:
            continue
        last_close = bar.close
        bar_date = date.fromisoformat(bar.date)
        should_exit, reason = check_trade_exit(trade, bar.close, bar_date)
        if should_exit:
            return {
                "status": "hit-target" if reason == "profit target" else (
                    "hit-stop" if reason == "stop loss" else "time-exit"
                ),
                "exit_date": bar.date,
                "exit_price": bar.close,
                "return_pct": (bar.close - entry_price) / entry_price,
                "reason": reason,
            }

    return {
        "status": "still-open",
        "exit_date": None,
        "exit_price": last_close,
        "return_pct": (last_close - entry_price) / entry_price if entry_price else 0.0,
        "reason": None,
    }
