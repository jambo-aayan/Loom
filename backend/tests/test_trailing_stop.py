"""Trailing stop with a derived high-water mark (#57, ADR-0018).

Trend Follower's trailing stop *is* the strategy — with only a fixed stop from entry, a winner
runs up and gives all of it back, because nothing ratchets. Volatility Breakout has the same need.
Both carried a documented approximation rather than the real thing.
"""

from datetime import date

import pytest

from loom.backtest.engine import check_exit
from loom.strategy import ExitPlan

ENTRY = 100.0
TODAY = date(2024, 6, 1)


def _check(plan: ExitPlan, price: float, peak: float | None = None, entry_date: str = "2024-05-01"):
    return check_exit(
        entry_price=ENTRY,
        entry_date=entry_date,
        exit_plan=plan,
        current_price=price,
        current_date=TODAY,
        peak_price=peak,
    )


def test_trailing_stop_fires_on_a_fall_from_the_peak_not_from_entry():
    """The whole point: the position is up 30% on entry and still exits, because it is 10% off
    its high. A fixed stop from entry would not fire until the price fell below 100."""
    assert _check(ExitPlan(trailing_stop_pct=0.10), price=130.0, peak=150.0) == (True, "trailing stop")


def test_trailing_stop_does_not_fire_while_the_position_holds_near_its_peak():
    assert _check(ExitPlan(trailing_stop_pct=0.10), price=145.0, peak=150.0) == (False, None)


def test_a_fixed_stop_and_a_trailing_stop_can_both_be_set_and_either_may_fire():
    """Different numbers doing different jobs: a tight fixed stop cuts a bad entry fast, a wider
    trailing stop lets a good one run."""
    plan = ExitPlan(stop_loss_pct=0.05, trailing_stop_pct=0.20)
    assert _check(plan, price=94.0, peak=101.0) == (True, "stop loss")
    assert _check(plan, price=120.0, peak=151.0) == (True, "trailing stop")


def test_a_plan_with_no_trailing_stop_is_unaffected_by_the_peak():
    plan = ExitPlan(profit_target_pct=0.5, stop_loss_pct=0.5)
    assert _check(plan, price=110.0, peak=200.0) == (False, None)


def test_an_unknown_peak_falls_back_to_the_entry_price():
    """A position with no history behind it is treated as never having risen, which makes the
    trailing stop behave as a stop from entry — conservative, never looser than intended."""
    assert _check(ExitPlan(trailing_stop_pct=0.10), price=89.0, peak=None) == (True, "trailing stop")
    assert _check(ExitPlan(trailing_stop_pct=0.10), price=95.0, peak=None) == (False, None)


def test_a_peak_below_entry_is_ignored():
    """The high-water mark starts at entry; a position that only ever fell has a peak of its
    entry price, not its best bad day."""
    assert _check(ExitPlan(trailing_stop_pct=0.10), price=95.0, peak=96.0) == (False, None)


def test_profit_target_still_takes_precedence_over_a_trailing_stop():
    plan = ExitPlan(profit_target_pct=0.10, trailing_stop_pct=0.10)
    assert _check(plan, price=115.0, peak=130.0) == (True, "profit target")


def test_exit_plan_round_trips_the_trailing_stop():
    """Plans are persisted as JSON on the Signal, so a field that does not survive as_dict is a
    field the live path never sees."""
    plan = ExitPlan(stop_loss_pct=0.05, trailing_stop_pct=0.12)
    assert plan.as_dict()["trailing_stop_pct"] == 0.12
    assert ExitPlan(**plan.as_dict()).trailing_stop_pct == 0.12


# --- both paths honour it, through the same shared decision ---------------------------

def test_a_backtest_with_a_trailing_stop_shows_it_firing():
    from loom.backtest.engine import run_backtest
    from loom.market_data.fixture import FixtureMarketDataSource
    from loom.strategies.trend_follower import TrendFollower
    from loom.strategy import StrategyConfig

    source = FixtureMarketDataSource()
    result = run_backtest(
        strategy=TrendFollower(StrategyConfig(params={"trailing_stop_pct": 0.04})),
        source=source,
        universe=source.universe(),
        start="2019-01-02",
        end="2024-12-27",
        starting_capital=10_000,
    )
    assert "trailing stop" in {t.exit_reason for t in result.trades if t.exit_reason}


def test_a_trailing_stop_is_off_by_default_so_existing_backtests_are_unchanged():
    from loom.strategies.trend_follower import DEFAULT_PARAMS as TREND_PARAMS
    from loom.strategies.volatility_breakout import DEFAULT_PARAMS as BREAKOUT_PARAMS

    assert TREND_PARAMS["trailing_stop_pct"] is None
    assert BREAKOUT_PARAMS["trailing_stop_pct"] is None


def test_the_exit_pass_records_a_trailing_stop_as_its_own_reason(session):
    from datetime import datetime

    from loom.exit_pass import run_exit_pass
    from loom.market_data.fixture import FixtureMarketDataSource
    from loom.models import Environment, ExitObservation
    from tests.test_exit_pass import _PricedBroker, _held

    # Entry at 75, peak well above it in the fixture's history, price fallen back.
    _held(session, entry=75.0, plan={"profit_target_pct": None, "stop_loss_pct": None,
                                     "time_exit_days": None, "trailing_stop_pct": 0.02})
    run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 60.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=datetime(2024, 3, 6, 12, 0),
    )

    observation = session.query(ExitObservation).one()
    assert observation.exit_reason == "trailing stop"
