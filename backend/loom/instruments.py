"""Symbol mapping layer (T0.3, decision D25): one record per Loom instrument, mapping Loom's own
identifier to every external namespace plus the exchange, currency and quoting unit.

Loom's identifier (`Instrument.id`) is what strategies, signals, orders and the DB already use
("VUSA.L", "TSLA"). It is never sent to an external service directly: each service gets its own
exchange-qualified symbol from here. An unqualified symbol is dangerous: Twelve Data resolves a
bare "VUSA" to a Munich or XETRA listing priced in EUR.

`quote_unit` is the unit the listing is quoted in on its exchange ("GBp" = pence). It is what every
data source is expected to report; a response reporting anything else is rejected (see
loom.market_data.boundary). Values below were read from Twelve Data's and Yahoo's own metadata on
22 Sep 2026 and must be confirmed against T212 instrument metadata (T1.3 builds this list from that
metadata automatically; until then it is static, like the T212 ticker map it replaces).
"""

from __future__ import annotations

from dataclasses import dataclass

from loom.calendars import Exchange


@dataclass(frozen=True)
class Instrument:
    id: str  # Loom's identifier, used in the DB, signals and strategies
    exchange: Exchange
    currency: str  # ISO major currency prices are normalised to: "GBP", "USD"
    quote_unit: str  # unit the listing is quoted in: "GBP", "GBp" (pence) or "USD"
    t212_ticker: str
    yahoo_symbol: str
    twelve_data_symbol: str  # always sent together with `exchange` (Twelve Data's `exchange` param)

    @property
    def is_lse(self) -> bool:
        return self.exchange == Exchange.LSE


class UnmappedInstrumentError(RuntimeError):
    """A caller used an identifier the registry doesn't know. Raised rather than guessing a symbol,
    which could silently fetch the wrong listing or send T212 a ticker it can't resolve."""


_INSTRUMENTS = (
    Instrument("VUSA.L", Exchange.LSE, "GBP", "GBP", "VUSAl_EQ", "VUSA.L", "VUSA"),  # Vanguard S&P 500 (Dist)
    Instrument("VWRL.L", Exchange.LSE, "GBP", "GBP", "VWRLl_EQ", "VWRL.L", "VWRL"),  # Vanguard FTSE All-World (Dist)
    Instrument("TSLA", Exchange.NASDAQ, "USD", "USD", "TSLA_US_EQ", "TSLA", "TSLA"),
    Instrument("NVDA", Exchange.NASDAQ, "USD", "USD", "NVDA_US_EQ", "NVDA", "NVDA"),
)

_BY_ID = {i.id: i for i in _INSTRUMENTS}
_BY_T212 = {i.t212_ticker: i for i in _INSTRUMENTS}


def get_instrument(instrument_id: str) -> Instrument:
    try:
        return _BY_ID[instrument_id]
    except KeyError:
        raise UnmappedInstrumentError(
            f"{instrument_id!r} is not in the instrument registry — add it to loom.instruments._INSTRUMENTS"
        ) from None


def get_by_t212_ticker(ticker: str) -> Instrument:
    try:
        return _BY_T212[ticker]
    except KeyError:
        raise UnmappedInstrumentError(
            f"T212 ticker {ticker!r} is not in the instrument registry — add it to loom.instruments._INSTRUMENTS"
        ) from None


def all_instruments() -> tuple[Instrument, ...]:
    return _INSTRUMENTS
