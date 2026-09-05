"""A deterministic, seeded synthetic OHLC generator. This is the default market data source for
the CLI backtest (story 41: "in seconds", not gated on a live Twelve Data key) and for tests
(Testing Decisions, issue #1: market data is one of the four external boundaries to fake).

Not a market-data provider in the ADR-0008 sense — TwelveDataSource is that. This exists so the
backtest is runnable and demoable with zero external dependencies.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta

from loom.market_data.base import MarketDataSource
from loom.strategy import Bar, InstrumentHistory

# A rough "personality" per instrument: (start_price, annual_drift, annual_vol)
_PROFILES: dict[str, tuple[float, float, float]] = {
    "VUSA.L": (75.0, 0.08, 0.14),  # low-vol index tracker
    "VWRL.L": (95.0, 0.07, 0.13),  # low-vol global tracker
    "TSLA": (220.0, 0.10, 0.55),  # high-vol single stock
    "NVDA": (450.0, 0.15, 0.45),  # high-vol single stock
}


def _business_days(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


class FixtureMarketDataSource(MarketDataSource):
    def __init__(self, profiles: dict[str, tuple[float, float, float]] | None = None):
        self.profiles = profiles or _PROFILES

    def universe(self) -> list[str]:
        return list(self.profiles.keys())

    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        start_d, end_d = date.fromisoformat(start), date.fromisoformat(end)
        start_price, drift, vol = self.profiles.get(instrument, (100.0, 0.06, 0.20))
        rng = random.Random(f"{instrument}:{start}:{end}")
        daily_drift = drift / 252
        daily_vol = vol / math.sqrt(252)

        bars: list[Bar] = []
        price = start_price
        for d in _business_days(start_d, end_d):
            change = rng.gauss(daily_drift, daily_vol)
            open_ = price
            close = max(0.01, price * (1 + change))
            high = max(open_, close) * (1 + abs(rng.gauss(0, daily_vol / 3)))
            low = min(open_, close) * (1 - abs(rng.gauss(0, daily_vol / 3)))
            bars.append(
                Bar(
                    date=d.isoformat(),
                    open=round(open_, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close, 4),
                    volume=rng.uniform(1_000, 100_000),
                )
            )
            price = close

        return InstrumentHistory(instrument=instrument, bars=tuple(bars))
