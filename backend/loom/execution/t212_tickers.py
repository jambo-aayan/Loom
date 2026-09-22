"""Translation between Loom's canonical instrument identifiers (the market-data-style tickers
strategies, signals and the DB all use — "TSLA", "VUSA.L") and Trading 212's own ticker namespace
("TSLA_US_EQ", "VUSAl_EQ").

The two namespaces are genuinely different, confirmed live: submitting an order with a bare
"TSLA" 404s, since T212 has no instrument by that name. `equity/positions` returns T212's own
ticker too, which would otherwise silently mismatch every DB-stored position and order.

Historically this was a hand-written four-entry dict, which was the right call while the universe
was four fixed instruments. ADR-0022 replaces it with the `instruments` table, synced from T212's
own metadata — `DbTickerMap` is that lookup. `LOOM_TO_T212` survives for two narrower jobs: a
fallback before the first sync has run, and a regression oracle for `derive_loom_ticker`, whose
inference rules were worked out from exactly these four confirmed examples.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

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


# T212 encodes the listing venue in the ticker itself. Only two forms are confirmed against a
# real account, and an unconfirmed one is deliberately NOT guessed: an instrument stored under a
# wrong Loom ticker would misattribute positions silently, which is the exact failure
# UnmappedInstrumentError exists to prevent. Unrecognised venues are skipped by the sync and
# reported, so the list below grows from evidence rather than from assumption.
_VENUE_SUFFIXES = {
    "_US": "",    # US listings carry no suffix in Loom's namespace: TSLA_US_EQ -> TSLA
    "l": ".L",    # London: VUSAl_EQ -> VUSA.L
}


def derive_loom_ticker(t212_ticker: str, short_name: str | None = None) -> str | None:
    """Loom's identifier for a T212 ticker, or None when the venue isn't one we can name
    confidently.

    Inferred from the four confirmed mappings above, which `test_t212_tickers` asserts this
    function still reproduces — so if T212's format ever drifts, the oracle fails rather than the
    sync quietly renaming the universe.
    """
    if not t212_ticker.endswith("_EQ"):
        return None
    base = t212_ticker[: -len("_EQ")]
    for marker, suffix in _VENUE_SUFFIXES.items():
        if marker.startswith("_"):
            if base.endswith(marker):
                return base[: -len(marker)] + suffix
        elif base.endswith(marker) and (short_name is None or base[: -len(marker)] == short_name):
            # A lowercase venue letter, distinguished from a symbol that merely ends in that
            # letter by checking it against T212's own shortName when we have it.
            return base[: -len(marker)] + suffix
    return None


class TickerMap(Protocol):
    """How a caller resolves tickers. A protocol rather than a concrete class so the T212 client
    can be given the DB-backed lookup in production and the static one in tests, without the
    client itself needing a database session."""

    def to_t212(self, instrument: str) -> str: ...

    def from_t212(self, ticker: str) -> str: ...


class StaticTickerMap:
    """The pre-ADR-0022 behaviour: the hand-written dict above. Still the fallback before the
    first instrument sync has run, so a fresh database can trade the original universe."""

    def to_t212(self, instrument: str) -> str:
        try:
            return LOOM_TO_T212[instrument]
        except KeyError:
            raise UnmappedInstrumentError(
                f"{instrument!r} has no T212 ticker mapping and no synced instrument row — "
                "run the instrument sync, or add it to loom.execution.t212_tickers.LOOM_TO_T212"
            ) from None

    def from_t212(self, ticker: str) -> str:
        try:
            return T212_TO_LOOM[ticker]
        except KeyError:
            raise UnmappedInstrumentError(
                f"T212 ticker {ticker!r} has no reverse mapping and no synced instrument row — "
                "run the instrument sync, or add it to loom.execution.t212_tickers.LOOM_TO_T212"
            ) from None


class DbTickerMap:
    """Resolves against the `instruments` table, falling back to the static map for anything not
    synced. The fallback matters on a fresh database and during the first sync; once the table is
    populated it is effectively dead, and the static map's four rows are a subset of it."""

    def __init__(self, session: Session):
        self._session = session
        self._static = StaticTickerMap()

    def to_t212(self, instrument: str) -> str:
        from loom.models import Instrument

        row = self._session.scalar(select(Instrument).where(Instrument.loom_ticker == instrument))
        return row.t212_ticker if row else self._static.to_t212(instrument)

    def from_t212(self, ticker: str) -> str:
        from loom.models import Instrument

        row = self._session.scalar(select(Instrument).where(Instrument.t212_ticker == ticker))
        return row.loom_ticker if row else self._static.from_t212(ticker)


_DEFAULT_MAP = StaticTickerMap()


def to_t212(instrument: str) -> str:
    return _DEFAULT_MAP.to_t212(instrument)


def from_t212(ticker: str) -> str:
    return _DEFAULT_MAP.from_t212(ticker)
