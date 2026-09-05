"""Shared contract test suite every Strategy implementation must pass (story 19): deterministic
given fixed inputs, always emits confidence + an exit plan, never mutates external state. Run
against `loom.strategies.ALL_STRATEGIES` — the single source of truth for the roster — so a new
strategy is covered automatically the moment it's registered, never rebuilt per strategy."""

import copy
import random

import pytest

from loom.strategies import ALL_STRATEGIES
from loom.strategy import AccountState, Bar, InstrumentHistory, MarketData, PositionSnapshot


def _sample_market_data() -> MarketData:
    # 260 bars (~a year of trading days) with a seeded pseudo-random walk — deterministic (fixed
    # once, not regenerated per call) but varied enough to exercise every strategy's longer
    # lookback windows (Trend Follower's 200d MA, Breakout's 60d squeeze lookback, etc).
    rng = random.Random("contract-suite-fixture")
    price = 100.0
    bars = []
    for i in range(260):
        price = max(1.0, price * (1 + rng.gauss(0.0003, 0.012)))
        d = f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
        bars.append(Bar(date=d, open=price, high=price * 1.01, low=price * 0.99, close=price))
    return MarketData(histories={"VUSA.L": InstrumentHistory("VUSA.L", tuple(bars))})


def _account_with_position() -> AccountState:
    return AccountState(cash=10_000, positions=(PositionSnapshot("VUSA.L", 5, 100.0, book_id="b1"),))


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
@pytest.mark.parametrize("account_factory", [lambda: AccountState(cash=10_000), _account_with_position])
def test_deterministic_given_fixed_inputs(strategy_cls, account_factory):
    strategy = strategy_cls()
    market_data = _sample_market_data()
    account = account_factory()

    first = strategy.generate_signals(market_data, account, account)
    second = strategy.generate_signals(market_data, account, account)

    assert first == second


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
@pytest.mark.parametrize("account_factory", [lambda: AccountState(cash=10_000), _account_with_position])
def test_every_signal_has_confidence_and_exit_plan(strategy_cls, account_factory):
    strategy = strategy_cls()
    account = account_factory()
    signals = strategy.generate_signals(_sample_market_data(), account, account)

    for signal in signals:
        assert 0.0 <= signal.confidence <= 1.0
        assert signal.exit_plan is not None


@pytest.mark.parametrize("strategy_cls", ALL_STRATEGIES)
@pytest.mark.parametrize("account_factory", [lambda: AccountState(cash=10_000), _account_with_position])
def test_never_mutates_inputs(strategy_cls, account_factory):
    strategy = strategy_cls()
    market_data = _sample_market_data()
    account = account_factory()
    before_md, before_acc = copy.deepcopy(market_data), copy.deepcopy(account)

    strategy.generate_signals(market_data, account, account)

    assert market_data == before_md
    assert account == before_acc
