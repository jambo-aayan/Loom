from loom.strategies.volatility_breakout import VolatilityBreakout
from loom.strategy import AccountState, Bar, InstrumentHistory, MarketData, PositionSnapshot, StrategyConfig

PARAMS = {"band_window": 5, "band_k": 2.0, "squeeze_lookback": 20, "normalization_multiple": 1.6}


def _squeeze_then_breakout_bars() -> tuple[Bar, ...]:
    bars = []
    # A wide-band warm-up so the squeeze lookback has something to compare against.
    for i in range(10):
        price = 100 + (5 if i % 2 == 0 else -5)
        bars.append(Bar(date=f"2024-01-{i + 1:02d}", open=price, high=price, low=price, close=price))
    # Then a tight squeeze (near-zero variance) for the band-width window.
    for i in range(5):
        bars.append(Bar(date=f"2024-01-{11 + i:02d}", open=100, high=100.05, low=99.95, close=100))
    # Confirmed breakout close, comfortably above the (now very tight) upper band.
    bars.append(Bar(date="2024-01-16", open=100, high=106, low=100, close=106))
    return tuple(bars)


def test_enters_on_confirmed_breakout_after_squeeze():
    strategy = VolatilityBreakout(StrategyConfig(params=PARAMS))
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", _squeeze_then_breakout_bars())})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    entries = [s for s in signals if s.instrument == "TSLA" and s.action == "buy"]
    assert entries


def test_no_entry_without_a_prior_squeeze():
    strategy = VolatilityBreakout(StrategyConfig(params=PARAMS))
    # Choppy throughout (never squeezes) then a spike — should not read as a breakout.
    bars = [
        Bar(date=f"2024-01-{i + 1:02d}", open=100, high=100, low=100, close=100 + (5 if i % 2 == 0 else -5))
        for i in range(15)
    ]
    bars.append(Bar(date="2024-01-16", open=100, high=112, low=100, close=112))
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", tuple(bars))})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    assert not [s for s in signals if s.instrument == "TSLA" and s.action == "buy"]


def test_exits_on_volatility_normalization():
    strategy = VolatilityBreakout(StrategyConfig(params=PARAMS))
    bars = list(_squeeze_then_breakout_bars())
    # A further wide swing after the breakout — band width re-expands well past its squeeze low.
    bars.append(Bar(date="2024-01-17", open=106, high=106, low=90, close=90))
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", tuple(bars))})
    account = AccountState(cash=10_000, positions=(PositionSnapshot("TSLA", 1, 106.0, book_id="b1"),))

    signals = strategy.generate_signals(market_data, account, account)

    exits = [s for s in signals if s.instrument == "TSLA" and s.action == "sell"]
    assert exits
