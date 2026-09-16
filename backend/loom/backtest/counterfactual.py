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

# A time exit is compared against elapsed calendar days, so the horizon has to reach past it far
# enough for a trading bar to exist on or after the threshold — a plan whose horizon stopped
# exactly at its own time exit could still miss it over a weekend.
_TIME_EXIT_MARGIN_DAYS = 7


def horizon_for(exit_plan: ExitPlan) -> int:
    """How far forward to simulate a shadow position carrying this plan (#54).

    Follows the plan rather than a fixed window: the horizon was 90 days while Trend Follower's
    own time exit is 180, so its counterfactuals could never resolve and always read `still-open`
    — the counterfactual layer exists to tell you whether your judgment added value, and one that
    structurally cannot resolve tells you nothing.

    A plan with no time exit keeps the default bound. Its target and stop may simply never be
    reached, and without a bound this becomes an unbounded walk over the instrument's whole
    remaining history.
    """
    if exit_plan.time_exit_days is None:
        return DEFAULT_MAX_HORIZON_DAYS
    return int(exit_plan.time_exit_days) + _TIME_EXIT_MARGIN_DAYS


def simulate_counterfactual(
    instrument: str,
    entry_date: str,
    entry_price: float,
    exit_plan: ExitPlan,
    source: MarketDataSource,
    max_horizon_days: int | None = None,
    as_of: date | None = None,
) -> dict:
    """`max_horizon_days` defaults to the plan's own horizon (see `horizon_for`); pass one
    explicitly to pin it."""
    max_horizon_days = horizon_for(exit_plan) if max_horizon_days is None else max_horizon_days
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
