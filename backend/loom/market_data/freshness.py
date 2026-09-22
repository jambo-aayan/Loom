"""Freshness rules for entry decisions (decision D25): no data or stale data for an instrument
means no entries for it in that scan. Exits are unaffected; they use T212's own prices (D15).

"Fresh" is anchored to the instrument's exchange calendar, so weekends, holidays and early closes
never make data look stale.
"""

from __future__ import annotations

from datetime import date, datetime

from loom.calendars import Exchange, last_completed_hourly_bar, last_completed_session


class StaleDataError(RuntimeError):
    """An instrument's latest bar is older than the latest bar that should exist by now."""


def is_daily_fresh(latest_bar: date, exchange: Exchange, now: datetime) -> bool:
    """True if the latest daily bar is at least the last completed session's. A newer, still-forming
    bar for today counts as fresh here; excluding it from daily indicators is the engine's
    previous-close rule (T1.1), not a freshness question."""
    return latest_bar >= last_completed_session(exchange, now)


def is_hourly_fresh(latest_bar_start: datetime, exchange: Exchange, now: datetime) -> bool:
    """True only if the latest bar *is* the hourly bar that just closed. The caller must already have
    dropped any still-forming bar; the hourly scan runs a few minutes after the hour so the
    just-closed bar has had time to arrive."""
    return latest_bar_start == last_completed_hourly_bar(exchange, now)
