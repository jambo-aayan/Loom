"""Ticket #36's explicit acceptance criterion: given fixture historical data with a known bucket
win rate, a new signal landing in that bucket gets the expected confidence."""

from loom import calibration
from loom.backtest.engine import TradeRecord
from loom.models import ConfigVersionStatus, StrategyConfigVersion, StrategyStyle
from loom.models import Strategy as StrategyModel
from loom.strategy import ExitPlan


def _trade(strength: float, pnl_positive: bool) -> TradeRecord:
    entry = 100.0
    exit_price = 110.0 if pnl_positive else 90.0
    return TradeRecord(
        instrument="X",
        entry_date="2024-01-01",
        entry_price=entry,
        quantity=1.0,
        exit_plan=ExitPlan(),
        exit_date="2024-01-05",
        exit_price=exit_price,
        entry_strength=strength,
    )


def test_compute_buckets_reports_realized_win_rate_per_bucket():
    # Two clean buckets: weak setups (strength ~1) mostly lose, strong setups (strength ~4)
    # mostly win — a known, deliberately clean split.
    trades = (
        [_trade(1.0 + i * 0.01, pnl_positive=False) for i in range(8)]
        + [_trade(1.0 + 0.5, pnl_positive=True)]  # one winner mixed into the weak group
        + [_trade(4.0 + i * 0.01, pnl_positive=True) for i in range(8)]
        + [_trade(4.0 + 0.5, pnl_positive=False)]  # one loser mixed into the strong group
    )

    buckets = calibration.compute_buckets(trades, num_buckets=2)

    assert len(buckets) == 2
    weak, strong = buckets
    assert weak["win_rate"] == 1 / 9
    assert strong["win_rate"] == 8 / 9
    assert weak["num_trades"] == 9
    assert strong["num_trades"] == 9


def test_lookup_confidence_returns_the_matching_buckets_win_rate():
    buckets = [
        {"min": 0.0, "max": 2.0, "win_rate": 0.2, "expectancy": -0.01, "num_trades": 10},
        {"min": 2.0, "max": 5.0, "win_rate": 0.8, "expectancy": 0.05, "num_trades": 10},
    ]

    assert calibration.lookup_confidence(buckets, 1.0) == 0.2
    assert calibration.lookup_confidence(buckets, 3.0) == 0.8


def test_lookup_confidence_extrapolates_to_nearest_edge_bucket():
    buckets = [
        {"min": 1.0, "max": 2.0, "win_rate": 0.3, "expectancy": 0.0, "num_trades": 5},
        {"min": 2.0, "max": 3.0, "win_rate": 0.7, "expectancy": 0.0, "num_trades": 5},
    ]

    assert calibration.lookup_confidence(buckets, 0.1) == 0.3  # weaker than anything seen
    assert calibration.lookup_confidence(buckets, 10.0) == 0.7  # stronger than anything seen


def test_lookup_confidence_with_no_calibration_returns_none():
    assert calibration.lookup_confidence([], 1.0) is None


def test_save_and_get_confidence_round_trips_through_the_database(session):
    strategy = StrategyModel(key="low_vol_compounder", name="Low-Vol Compounder", style=StrategyStyle.trading)
    session.add(strategy)
    session.flush()
    version = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params={}
    )
    session.add(version)
    session.commit()

    trades = [_trade(1.0, pnl_positive=False) for _ in range(3)] + [_trade(4.0, pnl_positive=True) for _ in range(3)]
    calibration.save_calibration(session, strategy.id, version.id, trades, num_buckets=2)

    assert calibration.get_confidence(session, strategy.id, version.id, 1.0) == 0.0
    assert calibration.get_confidence(session, strategy.id, version.id, 4.0) == 1.0


def test_get_confidence_with_no_saved_calibration_returns_none(session):
    strategy = StrategyModel(key="low_vol_compounder", name="Low-Vol Compounder", style=StrategyStyle.trading)
    session.add(strategy)
    session.flush()
    version = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params={}
    )
    session.add(version)
    session.commit()

    assert calibration.get_confidence(session, strategy.id, version.id, 1.0) is None
