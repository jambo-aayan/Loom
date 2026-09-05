from loom.fundamentals import FixtureFundamentalsProvider
from loom.strategies.value_quality_dip_buyer import ValueQualityDipBuyer
from loom.strategy import AccountState, Bar, InstrumentHistory, MarketData, PositionSnapshot, StrategyConfig

PARAMS = {"price_avg_window": 20, "dip_threshold_pct": 0.08}


def _dip_bars(days: int = 21, start: float = 100.0) -> tuple[Bar, ...]:
    bars = []
    price = start
    for i in range(days - 1):
        bars.append(Bar(date=f"2024-01-{i + 1:02d}", open=price, high=price * 1.001, low=price * 0.999, close=price))
    bars.append(Bar(date=f"2024-01-{days:02d}", open=price, high=price, low=price * 0.85, close=price * 0.85))
    return tuple(bars)


def test_enters_when_dip_and_quality_gate_both_pass():
    fundamentals = FixtureFundamentalsProvider(
        {"VUSA.L": {"pe_ratio": 18, "dividend_yield": 0.02, "debt_to_equity": 30, "sector": "X", "industry": "Y"}}
    )
    strategy = ValueQualityDipBuyer(StrategyConfig(params=PARAMS), fundamentals_provider=fundamentals)
    market_data = MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", _dip_bars())})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    entries = [s for s in signals if s.instrument == "VUSA.L" and s.action == "buy"]
    assert entries


def test_skips_when_pe_too_high():
    fundamentals = FixtureFundamentalsProvider(
        {"VUSA.L": {"pe_ratio": 40, "dividend_yield": 0.02, "debt_to_equity": 30, "sector": "X", "industry": "Y"}}
    )
    strategy = ValueQualityDipBuyer(StrategyConfig(params=PARAMS), fundamentals_provider=fundamentals)
    market_data = MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", _dip_bars())})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    assert not [s for s in signals if s.instrument == "VUSA.L" and s.action == "buy"]


def test_skips_when_dividend_yield_below_floor():
    fundamentals = FixtureFundamentalsProvider(
        {"VUSA.L": {"pe_ratio": 18, "dividend_yield": 0.001, "debt_to_equity": 30, "sector": "X", "industry": "Y"}}
    )
    strategy = ValueQualityDipBuyer(StrategyConfig(params=PARAMS), fundamentals_provider=fundamentals)
    market_data = MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", _dip_bars())})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    assert not [s for s in signals if s.instrument == "VUSA.L" and s.action == "buy"]


def test_skips_when_fundamentals_missing():
    strategy = ValueQualityDipBuyer(
        StrategyConfig(params=PARAMS), fundamentals_provider=FixtureFundamentalsProvider({})
    )
    market_data = MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", _dip_bars())})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    assert not [s for s in signals if s.instrument == "VUSA.L" and s.action == "buy"]


def test_no_entry_without_a_meaningful_dip():
    fundamentals = FixtureFundamentalsProvider(
        {"VUSA.L": {"pe_ratio": 18, "dividend_yield": 0.02, "debt_to_equity": 30, "sector": "X", "industry": "Y"}}
    )
    strategy = ValueQualityDipBuyer(StrategyConfig(params=PARAMS), fundamentals_provider=fundamentals)
    flat_bars = tuple(Bar(date=f"2024-01-{i + 1:02d}", open=100, high=100.1, low=99.9, close=100) for i in range(21))
    market_data = MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", flat_bars)})
    account = AccountState(cash=10_000)

    signals = strategy.generate_signals(market_data, account, account)

    assert not [s for s in signals if s.instrument == "VUSA.L" and s.action == "buy"]


def test_exits_held_position_on_profit_target():
    strategy = ValueQualityDipBuyer(StrategyConfig(params=PARAMS), fundamentals_provider=FixtureFundamentalsProvider())
    bars = _dip_bars()
    entry_price = bars[-1].close / 1.2
    market_data = MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", bars)})
    account = AccountState(cash=1_000, positions=(PositionSnapshot("VUSA.L", 5, entry_price, book_id="b1"),))

    signals = strategy.generate_signals(market_data, account, account)

    exits = [s for s in signals if s.instrument == "VUSA.L" and s.action == "sell"]
    assert exits


def test_from_config_uses_real_yfinance_source():
    from loom.market_data.yfinance_source import YFinanceSource

    strategy = ValueQualityDipBuyer.from_config({"dip_threshold_pct": 0.1})

    assert isinstance(strategy.fundamentals_provider, YFinanceSource)


def test_default_construction_stays_offline_and_deterministic():
    strategy = ValueQualityDipBuyer()

    assert isinstance(strategy.fundamentals_provider, FixtureFundamentalsProvider)
