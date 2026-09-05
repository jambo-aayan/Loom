from loom.strategies.trend_follower import TrendFollower
from loom.strategy import AccountState, Bar, InstrumentHistory, MarketData, PositionSnapshot, StrategyConfig


def _golden_cross_bars(short=10, long=30, days=40) -> tuple[Bar, ...]:
    """Flat at 100 for the long window, then a ramp up so the short MA crosses above the long MA
    on the final bar."""
    bars = []
    for i in range(days - 5):
        bars.append(Bar(date=f"2024-01-{i + 1:02d}", open=100, high=100.2, low=99.8, close=100))
    price = 100.0
    for i in range(5):
        price *= 1.05
        bars.append(Bar(date=f"2024-01-{days - 4 + i:02d}", open=price, high=price, low=price, close=price))
    return tuple(bars)


def _n_day_high_bars(window=10) -> tuple[Bar, ...]:
    bars = [Bar(date=f"2024-01-{i + 1:02d}", open=95, high=95, low=95, close=95) for i in range(window)]
    bars.append(Bar(date=f"2024-01-{window + 1:02d}", open=100, high=100, low=100, close=100))
    return tuple(bars)


def test_enters_on_golden_cross():
    strategy = TrendFollower(StrategyConfig(params={"short_window": 10, "long_window": 30}))
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", _golden_cross_bars())})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    entries = [s for s in signals if s.instrument == "TSLA" and s.action == "buy"]
    assert entries
    assert entries[0].exit_plan.stop_loss_pct is not None


def test_enters_on_n_day_high_breakout():
    strategy = TrendFollower(StrategyConfig(params={"short_window": 10, "long_window": 30, "breakout_window": 10}))
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", _n_day_high_bars(window=10))})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    entries = [s for s in signals if s.instrument == "TSLA" and s.action == "buy"]
    assert entries


def test_exits_on_death_cross():
    # A small short window (3) means a single sharp final-day drop pulls the short MA below the
    # long MA precisely on the last bar, rather than several days into a gradual decline.
    strategy = TrendFollower(StrategyConfig(params={"short_window": 3, "long_window": 10}))
    bars = [Bar(date=f"2024-01-{i + 1:02d}", open=100, high=100.2, low=99.8, close=100) for i in range(15)]
    bars.append(Bar(date="2024-01-16", open=100, high=100, low=80, close=80))
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", tuple(bars))})
    account = AccountState(cash=10_000, positions=(PositionSnapshot("TSLA", 10, 100.0, book_id="b1"),))

    signals = strategy.generate_signals(market_data, account, account)

    exits = [s for s in signals if s.instrument == "TSLA" and s.action == "sell"]
    assert exits
