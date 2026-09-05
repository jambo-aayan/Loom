from loom.strategies.low_vol_compounder import LowVolCompounder
from loom.strategy import AccountState, Bar, InstrumentHistory, MarketData, PositionSnapshot


def _flat_low_vol_bars(days: int = 60, start: float = 100.0) -> tuple[Bar, ...]:
    bars = []
    price = start
    for i in range(days):
        price *= 1.001  # tiny, steady uptrend -> low realized volatility
        d = f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
        bars.append(Bar(date=d, open=price, high=price * 1.001, low=price * 0.999, close=price))
    return tuple(bars)


def _volatile_bars(days: int = 60, start: float = 100.0) -> tuple[Bar, ...]:
    bars = []
    price = start
    for i in range(days):
        price *= 1.05 if i % 2 == 0 else 0.95
        d = f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
        bars.append(Bar(date=d, open=price, high=price * 1.05, low=price * 0.95, close=price))
    return tuple(bars)


def test_flags_low_volatility_uptrend_as_entry():
    strategy = LowVolCompounder()
    market_data = MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", _flat_low_vol_bars())})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    assert any(s.instrument == "VUSA.L" and s.action == "buy" for s in signals)


def test_skips_high_volatility_instrument():
    strategy = LowVolCompounder()
    market_data = MarketData(histories={"TSLA": InstrumentHistory("TSLA", _volatile_bars())})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    assert not any(s.instrument == "TSLA" for s in signals)


def test_skips_instrument_already_held():
    strategy = LowVolCompounder()
    market_data = MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", _flat_low_vol_bars())})
    account = AccountState(
        cash=10_000, positions=(PositionSnapshot("VUSA.L", 10, 100.0, book_id="b1"),)
    )

    signals = strategy.generate_signals(market_data, account, account)

    assert not any(s.action == "buy" and s.instrument == "VUSA.L" for s in signals)


def test_exits_held_position_on_profit_target():
    strategy = LowVolCompounder()
    bars = _flat_low_vol_bars()
    market_data = MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", bars)})
    entry_price = bars[-1].close / 1.1  # comfortably beyond the 4% default profit target
    account = AccountState(
        cash=1_000, positions=(PositionSnapshot("VUSA.L", 10, entry_price, book_id="b1"),)
    )

    signals = strategy.generate_signals(market_data, account, account)

    exits = [s for s in signals if s.instrument == "VUSA.L" and s.action == "sell"]
    assert exits and exits[0].signal_type == "exit"
