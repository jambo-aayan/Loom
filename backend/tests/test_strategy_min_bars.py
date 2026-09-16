"""Strategies declare the history they need, and the trading pass fetches enough of it (#50).

`lookback_days` was in *calendar* days while strategies count *trading bars*, so a 200-day
request yielded ~145 bars. Value/Quality Dip-Buyer (200 bars) emitted nothing at all, ever, and
Trend Follower's crossovers (201 bars) could never fire — meaning it could open a position in
demo and had no way to close it, since the death cross is its only coded exit.
"""

import math

import pytest

from loom.market_data.base import MarketDataSource
from loom.strategies import ALL_STRATEGIES
from loom.strategies.trend_follower import TrendFollower
from loom.strategies.value_quality_dip_buyer import ValueQualityDipBuyer
from loom.strategy import InstrumentHistory, StrategyConfig
from loom.trading_pass import calendar_days_for_bars, roster_min_bars


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
def test_every_strategy_declares_the_history_it_needs(strategy_cls):
    assert strategy_cls().min_bars() > 0


def test_min_bars_is_derived_from_parameters_not_hardcoded(strategy_cls=TrendFollower):
    """A parameter change that widens a window must widen the declared requirement with it —
    otherwise this recurs silently the next time a window is tuned."""
    narrow = strategy_cls(StrategyConfig(params={"long_window": 50}))
    wide = strategy_cls(StrategyConfig(params={"long_window": 200}))
    assert wide.min_bars() > narrow.min_bars()


def test_trend_follower_needs_more_than_a_calendar_200_day_window_yields():
    """The specific pairing that caused the bug: ~201 bars needed, ~145 delivered."""
    assert TrendFollower().min_bars() > 145
    assert ValueQualityDipBuyer().min_bars() > 145


def test_calendar_window_actually_yields_the_requested_bars():
    """Trading days are roughly 5/7 of calendar days before holidays. The conversion must
    over-fetch, not under-fetch — being short is the failure mode this ticket exists for."""
    for bars in (20, 51, 145, 200, 201, 260):
        days = calendar_days_for_bars(bars)
        weekdays = math.floor(days * 5 / 7)
        assert weekdays >= bars, f"{bars} bars -> {days} days only yields ~{weekdays} weekdays"


class _RecordingSource(MarketDataSource):
    """Captures the window the pass asks for, and answers with exactly that many trading days."""

    def __init__(self):
        self.requests: list[tuple[str, str]] = []

    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        self.requests.append((start, end))
        return InstrumentHistory(instrument=instrument, bars=())

    def universe(self) -> list[str]:
        return ["VUSA.L"]


def test_the_pass_requests_enough_history_for_the_hungriest_strategy(session):
    from datetime import date

    from loom.execution.broker import FakeBrokerClient
    from loom.models import Environment
    from loom.seed import seed_all_strategies
    from loom.trading_pass import run_trading_pass

    seed_all_strategies(session)
    source = _RecordingSource()
    run_trading_pass(
        Environment.demo,
        session,
        FakeBrokerClient(starting_cash=10_000, fill_price=100.0),
        source,
        universe=["VUSA.L"],
        as_of="2026-09-16",
    )

    assert source.requests, "the pass fetched no history at all"
    start, end = source.requests[0]
    span_days = (date.fromisoformat(end) - date.fromisoformat(start)).days
    assert span_days >= calendar_days_for_bars(roster_min_bars())
