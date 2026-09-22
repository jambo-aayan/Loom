"""Market data routed by exchange (decision D25): Yahoo is primary for LSE listings, Twelve Data is
primary for US listings with Yahoo as fallback. Every request goes through the instrument registry
(exchange-qualified symbols only) and every response through the unit boundary.

Replaces the old Twelve-Data-first composite source, which sent Yahoo-style symbols such as
"VUSA.L" to Twelve Data, where they don't resolve.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

from loom.instruments import get_instrument
from loom.market_data.base import MarketDataSource
from loom.market_data.boundary import NoMarketDataError, QuoteSource, normalise
from loom.market_data.freshness import StaleDataError, is_daily_fresh
from loom.strategy import InstrumentHistory


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RoutedMarketDataSource(MarketDataSource):
    def __init__(
        self,
        yahoo: QuoteSource,
        twelve_data: QuoteSource | None = None,
        now: Callable[[], datetime] = _utcnow,
    ):
        self.yahoo = yahoo
        self.twelve_data = twelve_data
        self._now = now

    def _sources_for(self, instrument_id: str) -> list[QuoteSource]:
        instrument = get_instrument(instrument_id)
        if instrument.is_lse or self.twelve_data is None:
            return [self.yahoo]
        return [self.twelve_data, self.yahoo]

    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        inst = get_instrument(instrument)
        failures = []
        errored = False
        for source in self._sources_for(instrument):
            try:
                raw = source.fetch_daily(inst, start, end)
            except Exception as exc:  # noqa: BLE001 — any provider failure moves on to the next source
                failures.append(f"{source.name}: {exc}")
                errored = True
                continue
            if not raw.bars:
                failures.append(f"{source.name}: no bars")
                continue
            # Deliberately outside the try: a unit mismatch is a data-integrity failure that must
            # surface loudly, not be papered over by quietly trying another source.
            return normalise(inst, raw, source.name)
        if not errored:
            # Every source answered, just with nothing in range (e.g. a window with no sessions):
            # an empty history, not an error. Callers that need data check for bars themselves.
            return InstrumentHistory(instrument=inst.id, bars=(), currency=inst.currency)
        raise NoMarketDataError(f"no market data for {instrument}: " + "; ".join(failures))

    def check_fresh(self, history: InstrumentHistory) -> None:
        latest = history.latest
        if latest is None:
            raise StaleDataError(f"{history.instrument}: no bars")
        exchange = get_instrument(history.instrument).exchange
        if not is_daily_fresh(date.fromisoformat(latest.date), exchange, self._now()):
            raise StaleDataError(f"{history.instrument}: latest daily bar is {latest.date}, which is stale")
