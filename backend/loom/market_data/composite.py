"""Twelve Data primary, yfinance backfill supplement — used whenever the primary source comes
back empty or errors (story 49: yfinance available as backfill, never the production dependency
on its own)."""

from __future__ import annotations

from loom.market_data.base import MarketDataSource
from loom.strategy import InstrumentHistory


class PrimaryWithBackfillSource(MarketDataSource):
    def __init__(self, primary: MarketDataSource, backfill: MarketDataSource):
        self.primary = primary
        self.backfill = backfill

    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        try:
            history = self.primary.get_history(instrument, start, end)
            if history.bars:
                return history
        except Exception:  # noqa: BLE001 — any primary-provider failure falls back, by design
            pass
        return self.backfill.get_history(instrument, start, end)
