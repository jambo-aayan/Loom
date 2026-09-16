"""`PositionSnapshot.entry_date` (#51) — the date the currently-open lot was opened.

The exit layer needs it for time exits and for the trailing stop's high-water mark, and the
dry-run audit reports hold duration from it. Derived from filled orders like the rest of the lot;
nothing new is persisted.
"""

from datetime import datetime

from loom.trading_pass import book_positions
from tests.test_book_positions_add_count import _fill, _seed_book


def test_entry_date_is_the_opening_buy(session):
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))

    assert book_positions(session, book.id)[0].entry_date == "2024-01-01"


def test_adds_do_not_move_the_entry_date(session):
    """The position is one economic unit under ADR-0018, opened once — an add increases it, it
    does not restart it. A time exit measured from the latest add would never fire on a position
    being repeatedly added to."""
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "add", 90.0, 5, datetime(2024, 1, 5))
    _fill(session, strategy, config, book, "add", 80.0, 5, datetime(2024, 1, 10))

    assert book_positions(session, book.id)[0].entry_date == "2024-01-01"


def test_entry_date_resets_after_a_full_exit_and_fresh_buy(session):
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))
    _fill(session, strategy, config, book, "sell", 95.0, 10, datetime(2024, 1, 10))
    _fill(session, strategy, config, book, "buy", 110.0, 8, datetime(2024, 1, 20))

    assert book_positions(session, book.id)[0].entry_date == "2024-01-20"


def test_lots_are_derived_in_fill_order_not_row_order(session):
    """`book_positions` did not order its orders, so the lot it derived depended on whatever order
    the database returned rows in. Average price is commutative so that never showed; add_count
    and entry_date are not. Seeded here with a later fill inserted before an earlier one.
    """
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "add", 90.0, 5, datetime(2024, 1, 5))
    _fill(session, strategy, config, book, "buy", 100.0, 10, datetime(2024, 1, 1))

    position = book_positions(session, book.id)[0]
    assert position.entry_date == "2024-01-01"
    assert position.add_count == 2
