"""Fundamentals boundary (P/E, dividend yield, debt/equity, sector/industry) for the
Value/Quality Dip-Buyer strategy (ADR-0009 #5) and sector drill-down (#38). Sourced from
yfinance (`market_data/yfinance_source.py`) via the existing market-data client boundary — no
new external dependency, per story 49. `FixtureFundamentalsProvider` is the faked boundary used
in tests and as Dip-Buyer's zero-network default, matching every other external boundary in this
app (Testing Decisions, issue #1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

# Sector rarely changes and every real lookup is a live yfinance network call — this
# process-lifetime cache keeps repeated Performance/History requests for the same instrument
# from re-fetching it, without needing a TTL or a persisted "instrument metadata" table (#38's
# "sliceable by sector" doesn't require one; this cache is enough to keep it fast at v1 scale).
_sector_cache: dict[str, str | None] = {}


class FundamentalsProvider(ABC):
    @abstractmethod
    def get_fundamentals(self, instrument: str) -> dict:
        """Returns at least: pe_ratio, dividend_yield, debt_to_equity, sector, industry. Any
        field can be None if unavailable — callers must treat that conservatively (skip the
        candidate), not default it."""
        raise NotImplementedError


def safe_sector_for(instrument: str, provider: FundamentalsProvider) -> str | None:
    """Sector/industry classification for drill-down (#38) — a network failure (the real
    yfinance-backed provider needs no key, but does need network) degrades to "unknown" rather
    than breaking the Performance/History page that asked for it."""
    if instrument in _sector_cache:
        return _sector_cache[instrument]
    try:
        sector = provider.get_fundamentals(instrument).get("sector")
    except Exception:  # noqa: BLE001 — degrade gracefully, this is a drill-down nicety, not core
        sector = None
    _sector_cache[instrument] = sector
    return sector


def filter_by_sector(
    items: list[T], instrument_of: Callable[[T], str], sector: str, provider: FundamentalsProvider
) -> list[T]:
    """Slices any list of trades/signals down to a sector/industry (#38), looking each distinct
    instrument's sector up once regardless of how many items share it. `instrument_of` extracts
    the instrument ticker from one item (a ClosedTrade's `.instrument`, a Signal's `.instrument`,
    ...) — the two call sites (Performance, History) differ only in that extraction."""
    sector_by_instrument = {i: safe_sector_for(i, provider) for i in {instrument_of(item) for item in items}}
    return [item for item in items if sector_by_instrument.get(instrument_of(item)) == sector]


# A rough "personality" per instrument, mirroring market_data/fixture.py's approach — enough to
# exercise the quality/value gates deterministically without a network call.
_FIXTURE_FUNDAMENTALS: dict[str, dict] = {
    "VUSA.L": {
        "pe_ratio": 22.0,
        "dividend_yield": 0.018,
        "debt_to_equity": 40.0,
        "sector": "Diversified",
        "industry": "Index Fund",
    },
    "VWRL.L": {
        "pe_ratio": 20.0,
        "dividend_yield": 0.017,
        "debt_to_equity": 35.0,
        "sector": "Diversified",
        "industry": "Index Fund",
    },
    "TSLA": {
        "pe_ratio": 65.0,
        "dividend_yield": 0.0,
        "debt_to_equity": 18.0,
        "sector": "Consumer Cyclical",
        "industry": "Auto Manufacturers",
    },
    "NVDA": {
        "pe_ratio": 55.0,
        "dividend_yield": 0.0003,
        "debt_to_equity": 22.0,
        "sector": "Technology",
        "industry": "Semiconductors",
    },
}


class FixtureFundamentalsProvider(FundamentalsProvider):
    def __init__(self, table: dict[str, dict] | None = None):
        self.table = table if table is not None else _FIXTURE_FUNDAMENTALS

    def get_fundamentals(self, instrument: str) -> dict:
        return self.table.get(
            instrument,
            {"pe_ratio": None, "dividend_yield": None, "debt_to_equity": None, "sector": None, "industry": None},
        )
