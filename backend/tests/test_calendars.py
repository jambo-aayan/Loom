"""Exchange calendar and trading-time arithmetic (T0.3, invariant 8: hold periods use trading
days/hours from the exchange calendar, never calendar days)."""

from datetime import UTC, date, datetime

import pytest

from loom.calendars import (
    Exchange,
    add_trading_days,
    add_trading_hours,
    hourly_bar_starts,
    is_open,
    is_session,
    last_completed_hourly_bar,
    last_completed_session,
    session_open_close,
    trading_days_between,
    trading_hours_between,
)

LSE, NYSE = Exchange.LSE, Exchange.NYSE


def utc(*args):
    return datetime(*args, tzinfo=UTC)


# --- sessions, weekends, holidays -------------------------------------------------------------


def test_weekends_and_uk_bank_holidays_are_not_lse_sessions():
    assert is_session(LSE, date(2026, 9, 22))  # Tuesday
    assert not is_session(LSE, date(2026, 9, 26))  # Saturday
    assert not is_session(LSE, date(2026, 12, 25))  # Christmas
    assert not is_session(LSE, date(2026, 12, 28))  # Boxing Day substitute (26th is a Saturday)
    assert not is_session(LSE, date(2026, 4, 3))  # Good Friday
    assert not is_session(LSE, date(2026, 4, 6))  # Easter Monday


def test_us_holidays_differ_from_uk():
    assert not is_session(NYSE, date(2026, 11, 26))  # Thanksgiving
    assert is_session(LSE, date(2026, 11, 26))
    assert is_session(NYSE, date(2026, 12, 28))  # a UK holiday, not a US one


def test_trading_days_skip_weekends_and_holidays():
    # Fri 18 Dec + 5 LSE trading days: 21, 22, 23, 24, 29 (25 and 28 are holidays).
    assert add_trading_days(LSE, date(2026, 12, 18), 5) == date(2026, 12, 29)
    assert trading_days_between(LSE, date(2026, 12, 18), date(2026, 12, 29)) == 5
    # The same span on NYSE only loses the 25th.
    assert add_trading_days(NYSE, date(2026, 12, 18), 5) == date(2026, 12, 28)


def test_twenty_trading_days_is_not_twenty_calendar_days():
    assert add_trading_days(LSE, date(2026, 9, 1), 20) == date(2026, 9, 29)


def test_add_trading_days_from_a_non_session_counts_from_the_last_session():
    # Saturday 19 Sep: the last session is Friday 18th, so +1 is Monday 21st.
    assert add_trading_days(LSE, date(2026, 9, 19), 1) == date(2026, 9, 21)
    assert add_trading_days(LSE, date(2026, 9, 21), -1) == date(2026, 9, 18)


def test_trading_days_between_is_zero_for_empty_ranges():
    assert trading_days_between(LSE, date(2026, 9, 22), date(2026, 9, 22)) == 0
    assert trading_days_between(LSE, date(2026, 9, 25), date(2026, 9, 27)) == 0  # Fri → Sun


# --- session hours and early closes ----------------------------------------------------------


def test_lse_session_hours_in_utc_follow_uk_daylight_saving():
    assert session_open_close(LSE, date(2026, 9, 22)) == (utc(2026, 9, 22, 7, 0), utc(2026, 9, 22, 15, 30))
    assert session_open_close(LSE, date(2026, 12, 1)) == (utc(2026, 12, 1, 8, 0), utc(2026, 12, 1, 16, 30))


def test_early_closes():
    # LSE closes at 12:30 on Christmas Eve; NYSE at 13:00 ET the day after Thanksgiving.
    assert session_open_close(LSE, date(2026, 12, 24))[1] == utc(2026, 12, 24, 12, 30)
    assert session_open_close(NYSE, date(2026, 11, 27))[1] == utc(2026, 11, 27, 18, 0)
    assert not is_open(LSE, utc(2026, 12, 24, 13, 0))
    assert is_open(LSE, utc(2026, 12, 23, 13, 0))


def test_is_open_edges_and_naive_datetimes_rejected():
    assert is_open(LSE, utc(2026, 9, 22, 7, 0))  # open is inclusive
    assert not is_open(LSE, utc(2026, 9, 22, 15, 30))  # close is exclusive
    assert not is_open(LSE, utc(2026, 9, 26, 10, 0))  # Saturday
    with pytest.raises(ValueError):
        is_open(LSE, datetime(2026, 9, 22, 10, 0))


def test_lse_has_nine_hourly_bars_and_fewer_on_an_early_close():
    bars = hourly_bar_starts(LSE, date(2026, 9, 22))
    assert len(bars) == 9
    assert bars[0] == utc(2026, 9, 22, 7, 0) and bars[-1] == utc(2026, 9, 22, 15, 0)  # 08:00 … 16:00 BST
    assert len(hourly_bar_starts(LSE, date(2026, 12, 24))) == 5  # 08:00 … 12:00, close 12:30
    assert len(hourly_bar_starts(NYSE, date(2026, 9, 22))) == 7  # 09:30 … 15:30 ET


# --- trading hours --------------------------------------------------------------------------


def test_forty_five_trading_hours_is_five_full_lse_sessions():
    # Tue 22 Sep 10:00 BST + 45 bars → Tue 29 Sep 10:00 BST.
    assert add_trading_hours(LSE, utc(2026, 9, 22, 9, 0), 45) == utc(2026, 9, 29, 9, 0)
    assert trading_hours_between(LSE, utc(2026, 9, 22, 9, 0), utc(2026, 9, 29, 9, 0)) == 45


def test_trading_hours_skip_overnight_weekends_and_holidays():
    # Thu 24 Dec 11:00 (early close, bars 08..12) + 3 bars: 12:00 on the 24th, then 25th and 28th
    # are holidays, so 08:00 and 09:00 on Tue 29th.
    assert add_trading_hours(LSE, utc(2026, 12, 24, 11, 0), 3) == utc(2026, 12, 29, 9, 0)


def test_trading_hours_from_mid_bar_and_from_outside_the_session():
    # 10:20 BST sits in the 10:00 bar; +1 is the 11:00 bar.
    assert add_trading_hours(LSE, utc(2026, 9, 22, 9, 20), 1) == utc(2026, 9, 22, 10, 0)
    # After Friday's close, counting starts at Monday's first bar: +1 is Monday 09:00 BST.
    assert add_trading_hours(LSE, utc(2026, 9, 25, 18, 0), 1) == utc(2026, 9, 28, 8, 0)
    # Before Tuesday's open, +1 is Tuesday 09:00 BST.
    assert add_trading_hours(LSE, utc(2026, 9, 22, 5, 0), 1) == utc(2026, 9, 22, 8, 0)


# --- freshness anchors ----------------------------------------------------------------------


def test_last_completed_session_before_and_after_the_close():
    # Tuesday 07:45 BST pre-open scan: the latest complete daily bar is Monday's.
    assert last_completed_session(LSE, utc(2026, 9, 22, 6, 45)) == date(2026, 9, 21)
    assert last_completed_session(LSE, utc(2026, 9, 22, 12, 0)) == date(2026, 9, 21)
    assert last_completed_session(LSE, utc(2026, 9, 22, 16, 0)) == date(2026, 9, 22)
    # Monday morning after a weekend: Friday.
    assert last_completed_session(LSE, utc(2026, 9, 28, 6, 45)) == date(2026, 9, 25)
    # Tue 29 Dec pre-open, after Christmas: Thursday 24th's early-closed session.
    assert last_completed_session(LSE, utc(2026, 12, 29, 7, 0)) == date(2026, 12, 24)


def test_last_completed_hourly_bar():
    # 10:05 BST: the 09:00 bar has closed, the 10:00 bar hasn't.
    assert last_completed_hourly_bar(LSE, utc(2026, 9, 22, 9, 5)) == utc(2026, 9, 22, 8, 0)
    # 16:35 BST: the short 16:00 bar closed at 16:30.
    assert last_completed_hourly_bar(LSE, utc(2026, 9, 22, 15, 35)) == utc(2026, 9, 22, 15, 0)
    # Monday 08:30 BST, before the first bar has closed: Friday's last bar.
    assert last_completed_hourly_bar(LSE, utc(2026, 9, 28, 7, 30)) == utc(2026, 9, 25, 15, 0)
