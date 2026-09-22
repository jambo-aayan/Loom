"""Maps Loom's instrument identifiers ("TSLA", "VUSA.L") to Trading 212's own ticker codes
("TSLA_US_EQ", "VUSAl_EQ") and back. T212 uses a completely different ticker namespace from the
market-data sources, confirmed live: submitting an order with a bare "TSLA" 404s, since T212's own
is "TSLA_US_EQ". `equity/positions` returns T212's own ticker too, which would otherwise silently
mismatch every DB-stored position/order using Loom's naming.

The mapping itself lives in the instrument registry (loom.instruments, T0.3), alongside every other
external symbol for the same instrument; this module keeps the T212 client's narrow interface.
"""

from __future__ import annotations

from loom.instruments import UnmappedInstrumentError, get_by_t212_ticker, get_instrument

__all__ = ["UnmappedInstrumentError", "from_t212", "to_t212"]


def to_t212(instrument: str) -> str:
    return get_instrument(instrument).t212_ticker


def from_t212(ticker: str) -> str:
    return get_by_t212_ticker(ticker).id
