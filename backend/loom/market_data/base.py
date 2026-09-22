from abc import ABC, abstractmethod

from loom.strategy import InstrumentHistory


class MarketDataSource(ABC):
    @abstractmethod
    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        """Return daily OHLC bars for `instrument` between `start` and `end` (inclusive,
        ISO dates). Never returns bars beyond `end` — callers (the backtest engine's fake
        clock) rely on that to avoid lookahead bias."""
        raise NotImplementedError

    def check_fresh(self, history: InstrumentHistory) -> None:
        """Raise loom.market_data.freshness.StaleDataError if `history` is too old to base an entry
        on right now (decision D25). Synthetic sources have no real clock, so the default accepts
        everything; real sources override this."""
