"""Shared contract test suite every Strategy implementation must pass (story 19): deterministic
given fixed inputs, always emits confidence + an exit plan, never mutates external state."""

import copy

import pytest

from loom.strategies.low_vol_compounder import LowVolCompounder
from loom.strategy import AccountState, Bar, InstrumentHistory, MarketData

ALL_STRATEGIES = [LowVolCompounder]


def _sample_market_data() -> MarketData:
    bars = tuple(
        Bar(
            date=f"2024-01-{i + 1:02d}",
            open=100 + i * 0.1,
            high=100.5 + i * 0.1,
            low=99.5 + i * 0.1,
            close=100 + i * 0.1,
        )
        for i in range(60)
    )
    return MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", bars)})


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
def test_deterministic_given_fixed_inputs(strategy_cls):
    strategy = strategy_cls()
    market_data = _sample_market_data()
    account = AccountState(cash=10_000)

    first = strategy.generate_signals(market_data, account, account)
    second = strategy.generate_signals(market_data, account, account)

    assert first == second


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
def test_every_signal_has_confidence_and_exit_plan(strategy_cls):
    strategy = strategy_cls()
    signals = strategy.generate_signals(_sample_market_data(), AccountState(cash=10_000), AccountState(cash=10_000))

    for signal in signals:
        assert 0.0 <= signal.confidence <= 1.0
        assert signal.exit_plan is not None


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
def test_never_mutates_inputs(strategy_cls):
    strategy = strategy_cls()
    market_data = _sample_market_data()
    account = AccountState(cash=10_000)
    before_md, before_acc = copy.deepcopy(market_data), copy.deepcopy(account)

    strategy.generate_signals(market_data, account, account)

    assert market_data == before_md
    assert account == before_acc
