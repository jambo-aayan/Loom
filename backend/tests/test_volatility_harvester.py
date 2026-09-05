from loom.strategies.volatility_harvester import VolatilityHarvester
from loom.strategy import AccountState, Bar, InstrumentHistory, MarketData, PositionSnapshot


def _bars_with_pullback(days: int = 30, start: float = 100.0) -> tuple[Bar, ...]:
    """Flat for most of the window, then a sharp final-day drop — a clean pullback below the
    rolling mean without needing a long history."""
    bars = []
    price = start
    for i in range(days - 1):
        bars.append(Bar(date=f"2024-01-{i + 1:02d}", open=price, high=price * 1.001, low=price * 0.999, close=price))
    bars.append(Bar(date=f"2024-01-{days:02d}", open=price, high=price, low=price * 0.85, close=price * 0.85))
    return tuple(bars)


def _bars_with_deep_pullback(days: int = 30, start: float = 100.0) -> tuple[Bar, ...]:
    """A tight, flat band (so the rolling stdev is small) with a modest final-day drop — enough
    to blow past the add-on-weakness z-score threshold while staying inside the stop-loss
    percentage, so the strategy reaches the add-on branch rather than exiting outright."""
    bars = []
    price = start
    for i in range(days - 1):
        bars.append(Bar(date=f"2024-01-{i + 1:02d}", open=price, high=price * 1.001, low=price * 0.999, close=price))
    bars.append(Bar(date=f"2024-01-{days:02d}", open=price, high=price, low=price * 0.97, close=price * 0.97))
    return tuple(bars)


def test_enters_on_pullback_below_rolling_mean():
    strategy = VolatilityHarvester()
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", _bars_with_pullback())})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    entries = [s for s in signals if s.instrument == "TSLA" and s.action == "buy"]
    assert entries
    assert entries[0].requires_manual_approval_override is None


def test_add_on_weakness_always_requires_manual_approval():
    strategy = VolatilityHarvester()
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", _bars_with_deep_pullback())})
    # Held near the top of the flat band, so the loss stays within the stop-loss percentage even
    # though the z-score has blown well past the add-on-weakness threshold (tight recent range).
    account = AccountState(cash=10_000, positions=(PositionSnapshot("TSLA", 10, 101.0, book_id="b1"),))

    signals = strategy.generate_signals(market_data, account, account)

    add_ons = [s for s in signals if s.instrument == "TSLA" and s.action == "add"]
    assert add_ons, "expected an add-on-weakness signal for a deep pullback while already holding"
    assert add_ons[0].requires_manual_approval_override is True


def test_trims_on_bounce_back_to_mean():
    strategy = VolatilityHarvester()
    # A small, non-zero-variance oscillation around 100 (so the z-score is defined), ending
    # exactly on the mean — comfortably above the exit_z_score threshold.
    bars = tuple(
        Bar(date=f"2024-01-{i + 1:02d}", open=100, high=100.2, low=99.8, close=100 + (0.5 if i % 2 == 0 else -0.5))
        for i in range(29)
    ) + (Bar(date="2024-01-30", open=100, high=100.2, low=99.8, close=100.0),)
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", bars)})
    account = AccountState(cash=10_000, positions=(PositionSnapshot("TSLA", 10, 90.0, book_id="b1"),))

    signals = strategy.generate_signals(market_data, account, account)

    exits = [s for s in signals if s.instrument == "TSLA" and s.action == "sell"]
    assert exits
