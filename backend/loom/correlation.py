"""Cross-`Book` correlation (story 72, ticket #38): "are these strategies actually diversifying,
or all moving together." Each Book's closed trades are event-driven (no daily NAV), so returns
are bucketed into weekly realized P&L before correlating — the same honest simplification
`loom.evaluation` already documents for Sharpe/Sortino on trade-level series."""

from __future__ import annotations

import statistics

from loom.trade_reconstruction import ClosedTrade


def weekly_pnl_series(trades: list[ClosedTrade]) -> dict[str, float]:
    series: dict[str, float] = {}
    for trade in trades:
        week_key = trade.exit_date.strftime("%G-W%V")
        series[week_key] = series.get(week_key, 0.0) + trade.pnl
    return series


def pearson_correlation(a: dict[str, float], b: dict[str, float]) -> float | None:
    weeks = sorted(set(a) | set(b))
    if len(weeks) < 2:
        return None
    xs = [a.get(w, 0.0) for w in weeks]
    ys = [b.get(w, 0.0) for w in weeks]
    if statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
        return None  # a constant series has no defined correlation
    return statistics.correlation(xs, ys)


def compute_correlation_matrix(books: list[tuple[str, str]], trades_by_book: dict[str, list[ClosedTrade]]) -> dict:
    """`books` is [(book_id, book_name), ...]; `trades_by_book` maps book_id -> its closed trades."""
    series_by_book = {book_id: weekly_pnl_series(trades_by_book.get(book_id, [])) for book_id, _ in books}
    matrix = [
        [pearson_correlation(series_by_book[a_id], series_by_book[b_id]) for b_id, _ in books] for a_id, _ in books
    ]
    return {"books": [{"id": bid, "name": name} for bid, name in books], "matrix": matrix}
