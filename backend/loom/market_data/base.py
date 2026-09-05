from abc import ABC, abstractmethod

from loom.strategy import InstrumentHistory


class MarketDataSource(ABC):
    @abstractmethod
    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        """Return daily OHLC bars for `instrument` between `start` and `end` (inclusive,
        ISO dates). Never returns bars beyond `end` — callers (the backtest engine's fake
        clock) rely on that to avoid lookahead bias."""
        raise NotImplementedError
