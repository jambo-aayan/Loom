"""Maps Loom's canonical instrument identifiers (the market-data-style tickers strategies,
signals, and the DB all use — "TSLA", "VUSA.L") to Trading 212's own internal ticker codes
("TSLA_US_EQ", "VUSAl_EQ") and back. T212 uses a completely different ticker namespace from
Twelve Data/yfinance, confirmed live: submitting an order with a bare "TSLA" 404s, since T212 has
no instrument by that name — its own is "TSLA_US_EQ". `equity/positions` returns T212's own
ticker too, which would otherwise silently mismatch every DB-stored position/order using the
market-data naming.

Deliberately a static map, not a dynamic lookup against T212's `/equity/metadata/instruments` (a
multi-thousand-row response) on every call — v1's universe is 4 fixed instruments
(loom.api.routers.trading.DEFAULT_UNIVERSE). Extend this dict alongside the universe if it grows;
a dynamic metadata-backed lookup is worth building once the universe is no longer a small fixed
list, not before.
"""

from __future__ import annotations

# Loom instrument -> T212 ticker. Looked up live against T212's own /equity/metadata/instruments
# for this demo account (Sep 2026) — pick the listing matching the market/currency Loom's own
# universe implies (GBP/LSE for the ".L"-suffixed ones, US common stock for the others).
LOOM_TO_T212 = {
    "VUSA.L": "VUSAl_EQ",  # Vanguard S&P 500 (Dist), GBP, LSE listing
    "VWRL.L": "VWRLl_EQ",  # Vanguard FTSE All-World (Dist), GBP, LSE listing
    "TSLA": "TSLA_US_EQ",
    "NVDA": "NVDA_US_EQ",
}

T212_TO_LOOM = {v: k for k, v in LOOM_TO_T212.items()}


class UnmappedInstrumentError(RuntimeError):
    """A caller used an instrument identifier this map doesn't know — raised rather than sending
    T212 something it can't resolve (another 404) or silently returning a position under the
    wrong name (a DB/broker mismatch that would misattribute or double-count it)."""


def to_t212(instrument: str) -> str:
    try:
        return LOOM_TO_T212[instrument]
    except KeyError:
        raise UnmappedInstrumentError(
            f"{instrument!r} has no T212 ticker mapping — add it to loom.execution.t212_tickers.LOOM_TO_T212"
        ) from None


def from_t212(ticker: str) -> str:
    try:
        return T212_TO_LOOM[ticker]
    except KeyError:
        raise UnmappedInstrumentError(
            f"T212 ticker {ticker!r} has no reverse mapping — add it to loom.execution.t212_tickers.LOOM_TO_T212"
        ) from None
