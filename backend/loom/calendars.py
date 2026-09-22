"""Exchange calendars and trading-time arithmetic (T0.3, invariant 8).

Every hold period in Loom counts trading days or trading hours on the instrument's own exchange
calendar, never calendar days: weekends, bank holidays and early closes all come from
`exchange_calendars` (XLON for the LSE, XNYS for US listings), not from anything hand-rolled.

Trading hours are hourly *bars*, matching the research data (Yahoo 60-minute bars): bars start at
the session open and every hour after it, and the last bar of a session is cut short by the close.
A full LSE session (08:00–16:30) therefore has 9 bars (08:00 … 16:00), so "45 trading hours" is
five full LSE sessions. An early close (12:30 on 24 and 31 December) has fewer bars.

All datetimes taken and returned are timezone-aware UTC; dates are exchange-local session dates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import Enum
from functools import cache

import exchange_calendars as xcals
import pandas as pd

_HOUR = timedelta(hours=1)


class Exchange(str, Enum):
    LSE = "LSE"
    NYSE = "NYSE"
    NASDAQ = "NASDAQ"


# NASDAQ and NYSE share one trading calendar (XNYS), as exchange_calendars itself documents.
_CALENDAR_CODE = {Exchange.LSE: "XLON", Exchange.NYSE: "XNYS", Exchange.NASDAQ: "XNYS"}


@cache
def _calendar(exchange: Exchange) -> xcals.ExchangeCalendar:
    return xcals.get_calendar(_CALENDAR_CODE[exchange], start="2015-01-01")


def _utc(ts: pd.Timestamp) -> datetime:
    return ts.tz_convert("UTC").to_pydatetime()


def _require_aware(moment: datetime) -> pd.Timestamp:
    if moment.tzinfo is None:
        raise ValueError(f"{moment!r} is naive; trading-time helpers only take timezone-aware datetimes")
    return pd.Timestamp(moment).tz_convert("UTC")


def is_session(exchange: Exchange, day: date) -> bool:
    """True if `day` is a trading day on `exchange` (not a weekend or holiday)."""
    return bool(_calendar(exchange).is_session(pd.Timestamp(day)))


def session_open_close(exchange: Exchange, day: date) -> tuple[datetime, datetime]:
    """UTC open and close for session `day`, early closes included. Raises for a non-session."""
    cal = _calendar(exchange)
    ts = pd.Timestamp(day)
    if not cal.is_session(ts):
        raise ValueError(f"{day} is not a trading day on {exchange.value}")
    return _utc(cal.session_open(ts)), _utc(cal.session_close(ts))


def is_open(exchange: Exchange, moment: datetime) -> bool:
    """True if `exchange` is in its regular session at `moment` (open inclusive, close exclusive)."""
    cal = _calendar(exchange)
    ts = _require_aware(moment)
    day = ts.tz_convert(cal.tz).normalize().tz_localize(None)
    if not cal.is_session(day):
        return False
    return cal.session_open(day) <= ts < cal.session_close(day)


def add_trading_days(exchange: Exchange, day: date, n: int) -> date:
    """The session `n` trading days after `day` (or before, for negative `n`). `day` itself need not
    be a session: counting starts from the nearest session on the side being counted towards."""
    if n == 0:
        raise ValueError("n must be non-zero")
    cal = _calendar(exchange)
    ts = pd.Timestamp(day)
    if n > 0:
        anchor = cal.date_to_session(ts, direction="previous")
    else:
        anchor = cal.date_to_session(ts, direction="next")
    return cal.session_offset(anchor, n).date()


def trading_days_between(exchange: Exchange, start: date, end: date) -> int:
    """Number of sessions in the half-open interval (start, end]: how many trading days have passed
    since `start` by the end of `end`. Zero when end <= start."""
    if end <= start:
        return 0
    sessions = _calendar(exchange).sessions_in_range(pd.Timestamp(start + timedelta(days=1)), pd.Timestamp(end))
    return len(sessions)


def hourly_bar_starts(exchange: Exchange, day: date) -> list[datetime]:
    """UTC start times of the hourly bars of session `day`: the open, then every hour before the close."""
    open_, close = session_open_close(exchange, day)
    starts = []
    t = open_
    while t < close:
        starts.append(t)
        t += _HOUR
    return starts


def _bar_starts_from(exchange: Exchange, moment: datetime, sessions_needed: int) -> list[datetime]:
    cal = _calendar(exchange)
    ts = _require_aware(moment)
    local_day = ts.tz_convert(cal.tz).normalize().tz_localize(None)
    first = cal.date_to_session(local_day, direction="next")
    sessions = cal.sessions_window(first, sessions_needed)
    return [start for s in sessions for start in hourly_bar_starts(exchange, s.date())]


def add_trading_hours(exchange: Exchange, moment: datetime, n: int) -> datetime:
    """The start of the hourly bar `n` bars after the bar containing `moment`. A `moment` outside the
    session counts from the next bar to open. E.g. LSE 10:00 Monday + 45 → 10:00 the following Monday
    (5 full sessions of 9 bars), holidays and early closes skipped."""
    if n <= 0:
        raise ValueError("n must be positive")
    at = _require_aware(moment).to_pydatetime()
    sessions_needed = n // 5 + 3  # >= 5 bars in any session, plus slack for the current one
    starts = _bar_starts_from(exchange, at, sessions_needed)
    # Index of the bar containing `at`, or of the next bar to open if `at` falls between sessions.
    containing = max((i for i, s in enumerate(starts) if s <= at), default=None)
    if containing is not None and not is_open(exchange, at):
        containing += 1  # after today's close: the "current" bar is the next session's first
    index = 0 if containing is None else containing
    return starts[index + n]


def trading_hours_between(exchange: Exchange, start: datetime, end: datetime) -> int:
    """Number of hourly bars that *start* in the half-open interval (start, end]."""
    s, e = _require_aware(start).to_pydatetime(), _require_aware(end).to_pydatetime()
    if e <= s:
        return 0
    # A day of slack either side: session labels are exchange-local dates, `start`/`end` are UTC.
    sessions = _calendar(exchange).sessions_in_range(
        pd.Timestamp(s.date() - timedelta(days=1)), pd.Timestamp(e.date() + timedelta(days=1))
    )
    return sum(1 for d in sessions for b in hourly_bar_starts(exchange, d.date()) if s < b <= e)


def last_completed_session(exchange: Exchange, now: datetime) -> date:
    """The most recent session whose close is at or before `now`: the date the latest *complete*
    daily bar should carry. At 07:45 on a Tuesday this is Monday; at 17:00 Tuesday it's Tuesday."""
    cal = _calendar(exchange)
    ts = _require_aware(now)
    day = ts.tz_convert(cal.tz).normalize().tz_localize(None)
    session = cal.date_to_session(day, direction="previous")
    if cal.session_close(session) > ts:
        session = cal.previous_session(session)
    return session.date()


def last_completed_hourly_bar(exchange: Exchange, now: datetime) -> datetime:
    """Start time (UTC) of the most recent hourly bar that has fully closed by `now`."""
    ts = _require_aware(now).to_pydatetime()
    cal = _calendar(exchange)
    day = pd.Timestamp(ts).tz_convert(cal.tz).normalize().tz_localize(None)
    session = cal.date_to_session(day, direction="previous")
    for _ in range(10):  # walk back over at most a long holiday weekend
        starts = hourly_bar_starts(exchange, session.date())
        _, close = session_open_close(exchange, session.date())
        ends = starts[1:] + [close]
        done = [s for s, end in zip(starts, ends) if end <= ts]
        if done:
            return done[-1]
        session = cal.previous_session(session)
    raise RuntimeError(f"no completed hourly bar found on {exchange.value} before {now}")
