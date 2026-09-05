"""Fundamentals boundary (P/E, dividend yield, debt/equity, sector/industry) for the
Value/Quality Dip-Buyer strategy (ADR-0009 #5) and sector drill-down (#38). Sourced from
yfinance (`market_data/yfinance_source.py`) via the existing market-data client boundary — no
new external dependency, per story 49. `FixtureFundamentalsProvider` is the faked boundary used
in tests and as Dip-Buyer's zero-network default, matching every other external boundary in this
app (Testing Decisions, issue #1)."""

from __future__ import annotations

from abc import ABC, abstractmethod


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
    try:
        return provider.get_fundamentals(instrument).get("sector")
    except Exception:  # noqa: BLE001 — degrade gracefully, this is a drill-down nicety, not core
        return None


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
