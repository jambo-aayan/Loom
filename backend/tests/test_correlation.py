from datetime import datetime

from loom.correlation import compute_correlation_matrix, pearson_correlation, weekly_pnl_series
from loom.trade_reconstruction import ClosedTrade


def _trade(day: int, pnl: float) -> ClosedTrade:
    entry_price = 100.0
    return ClosedTrade(
        instrument="X",
        entry_date=datetime(2024, 1, day),
        exit_date=datetime(2024, 1, day),
        entry_price=entry_price,
        exit_price=entry_price + pnl,
        quantity=1.0,
    )


def test_weekly_pnl_series_buckets_by_iso_week():
    trades = [_trade(1, 10), _trade(2, 5), _trade(8, -20)]  # Jan 1-2 same week, Jan 8 next week

    series = weekly_pnl_series(trades)

    assert len(series) == 2
    assert sum(series.values()) == -5


def test_pearson_correlation_perfectly_correlated_series():
    a = {"2024-W01": 10.0, "2024-W02": 20.0, "2024-W03": 30.0}
    b = {"2024-W01": 100.0, "2024-W02": 200.0, "2024-W03": 300.0}

    assert round(pearson_correlation(a, b), 4) == 1.0


def test_pearson_correlation_inversely_correlated_series():
    a = {"2024-W01": 10.0, "2024-W02": 20.0, "2024-W03": 30.0}
    b = {"2024-W01": -10.0, "2024-W02": -20.0, "2024-W03": -30.0}

    assert round(pearson_correlation(a, b), 4) == -1.0


def test_pearson_correlation_none_with_fewer_than_two_overlapping_weeks():
    assert pearson_correlation({"2024-W01": 1.0}, {"2024-W01": 2.0}) is None
    assert pearson_correlation({}, {}) is None


def test_pearson_correlation_none_for_constant_series():
    a = {"2024-W01": 5.0, "2024-W02": 5.0}
    b = {"2024-W01": 1.0, "2024-W02": 2.0}

    assert pearson_correlation(a, b) is None


def test_compute_correlation_matrix_shape_and_diagonal():
    trades_a = [_trade(1, 10), _trade(8, 20), _trade(15, -5)]
    trades_b = [_trade(1, -10), _trade(8, -20), _trade(15, 5)]

    result = compute_correlation_matrix(
        [("book-a", "Book A"), ("book-b", "Book B")],
        {"book-a": trades_a, "book-b": trades_b},
    )

    assert [b["id"] for b in result["books"]] == ["book-a", "book-b"]
    assert len(result["matrix"]) == 2
    assert round(result["matrix"][0][0], 4) == 1.0  # a book always perfectly correlates with itself
    assert round(result["matrix"][0][1], 4) == -1.0
