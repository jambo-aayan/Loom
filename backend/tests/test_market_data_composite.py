from loom.market_data.base import MarketDataSource
from loom.market_data.composite import PrimaryWithBackfillSource
from loom.strategy import Bar, InstrumentHistory


class _StubSource(MarketDataSource):
    def __init__(self, bars=(), raises: bool = False):
        self._bars = bars
        self._raises = raises
        self.calls = 0

    def get_history(self, instrument, start, end):
        self.calls += 1
        if self._raises:
            raise RuntimeError("provider down")
        return InstrumentHistory(instrument, self._bars)


def test_uses_primary_when_it_returns_data():
    primary = _StubSource(bars=(Bar("2024-01-01", 1, 1, 1, 1),))
    backfill = _StubSource(bars=(Bar("2024-01-01", 2, 2, 2, 2),))
    source = PrimaryWithBackfillSource(primary, backfill)

    history = source.get_history("X", "2024-01-01", "2024-01-02")

    assert history.bars[0].close == 1
    assert backfill.calls == 0


def test_falls_back_when_primary_raises():
    primary = _StubSource(raises=True)
    backfill = _StubSource(bars=(Bar("2024-01-01", 2, 2, 2, 2),))
    source = PrimaryWithBackfillSource(primary, backfill)

    history = source.get_history("X", "2024-01-01", "2024-01-02")

    assert history.bars[0].close == 2


def test_falls_back_when_primary_returns_no_bars():
    primary = _StubSource(bars=())
    backfill = _StubSource(bars=(Bar("2024-01-01", 3, 3, 3, 3),))
    source = PrimaryWithBackfillSource(primary, backfill)

    history = source.get_history("X", "2024-01-01", "2024-01-02")

    assert history.bars[0].close == 3
