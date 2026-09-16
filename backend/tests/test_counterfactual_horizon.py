"""Counterfactual horizon follows the plan being simulated (#54).

The horizon was a fixed 90 days, shorter than some strategies' own time exits — so a Signal whose
plan says "exit after 180 days" could never reach it and came back `still-open` regardless of what
actually happened. Trend Follower's counterfactuals were structurally truncated.
"""

from loom.backtest.counterfactual import DEFAULT_MAX_HORIZON_DAYS, horizon_for, simulate_counterfactual
from loom.market_data.fixture import FixtureMarketDataSource
from loom.strategy import ExitPlan


def test_horizon_covers_a_long_time_exit():
    assert horizon_for(ExitPlan(time_exit_days=180)) > 180


def test_horizon_covers_a_short_time_exit_without_shrinking_below_it():
    assert horizon_for(ExitPlan(time_exit_days=20)) >= 20


def test_a_plan_with_no_time_exit_is_still_bounded():
    """Target and stop may simply never be reached. Without a bound this becomes an unbounded
    simulation over the instrument's entire remaining history."""
    horizon = horizon_for(ExitPlan(profit_target_pct=0.5, stop_loss_pct=0.5))
    assert 0 < horizon <= DEFAULT_MAX_HORIZON_DAYS


def test_a_long_time_exit_now_resolves_instead_of_staying_open():
    plan = ExitPlan(profit_target_pct=5.0, stop_loss_pct=5.0, time_exit_days=180)
    outcome = simulate_counterfactual(
        instrument="VUSA.L",
        entry_date="2023-01-03",
        entry_price=75.0,
        exit_plan=plan,
        source=FixtureMarketDataSource(),
    )
    assert outcome["status"] == "time-exit"
    assert outcome["exit_date"] is not None


def test_plans_shorter_than_the_old_fixed_window_are_unchanged():
    plan = ExitPlan(profit_target_pct=5.0, stop_loss_pct=5.0, time_exit_days=20)
    outcome = simulate_counterfactual(
        instrument="VUSA.L",
        entry_date="2023-01-03",
        entry_price=75.0,
        exit_plan=plan,
        source=FixtureMarketDataSource(),
    )
    assert outcome["status"] == "time-exit"


def test_an_explicit_horizon_still_wins():
    """The caller can still pin it — the derivation is a default, not a policy."""
    assert simulate_counterfactual(
        instrument="VUSA.L",
        entry_date="2023-01-03",
        entry_price=75.0,
        exit_plan=ExitPlan(time_exit_days=180),
        source=FixtureMarketDataSource(),
        max_horizon_days=5,
    )["status"] == "still-open"
