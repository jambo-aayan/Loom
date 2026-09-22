"""The market-data boundary (T0.3, invariant 9): everything a price source returns passes through
`normalise` before any strategy, sizing or storage code sees it.

`normalise` checks that the unit the source *reported* matches the listing's quoting unit in the
instrument registry, and converts to the major currency (GBp → GBP by dividing by 100). A missing or
different unit is a `UnitMismatchError`, never a guess: a pence price read as pounds would make every
stop fire instantly or never.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from loom.instruments import Instrument
from loom.strategy import Bar, InstrumentHistory

# Reported unit → (major currency, multiplier to reach it). "GBX" is the ISO-style alias for pence.
_UNITS: dict[str, tuple[str, float]] = {
    "GBP": ("GBP", 1.0),
    "GBp": ("GBP", 0.01),
    "GBX": ("GBP", 0.01),
    "USD": ("USD", 1.0),
}
_ALIASES = {"GBX": "GBp"}


class UnitMismatchError(RuntimeError):
    """A source reported prices in a unit other than the listing's quoting unit (or none at all)."""


class NoMarketDataError(RuntimeError):
    """Every source for an instrument failed or returned no bars."""


@dataclass(frozen=True)
class RawHistory:
    """Bars exactly as a source returned them, before normalisation."""

    symbol: str  # the source-specific symbol that was requested
    reported_unit: str | None  # the price unit the source itself reported in its response
    bars: tuple[Bar, ...]


class QuoteSource(Protocol):
    """A price source that is only ever asked for an instrument's own exchange-qualified symbol."""

    name: str

    def fetch_daily(self, instrument: Instrument, start: str, end: str) -> RawHistory: ...


def normalise(instrument: Instrument, raw: RawHistory, source_name: str) -> InstrumentHistory:
    reported = _ALIASES.get(raw.reported_unit or "", raw.reported_unit)
    if reported != instrument.quote_unit:
        raise UnitMismatchError(
            f"{source_name} returned {instrument.id} ({raw.symbol}) in {raw.reported_unit!r}; "
            f"the listing is quoted in {instrument.quote_unit!r}"
        )
    currency, factor = _UNITS[reported]
    if currency != instrument.currency:
        raise UnitMismatchError(
            f"{instrument.id}: unit {reported!r} is {currency}, but the instrument trades in {instrument.currency}"
        )
    bars = tuple(
        replace(b, open=b.open * factor, high=b.high * factor, low=b.low * factor, close=b.close * factor)
        for b in raw.bars
    )
    return InstrumentHistory(instrument=instrument.id, bars=bars, currency=currency)
