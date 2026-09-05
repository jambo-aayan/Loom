from datetime import datetime, timedelta

from loom import strategies  # noqa: F401
from loom.execution.broker import FakeBrokerClient
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import (
    ApprovalMode,
    ConfigVersionStatus,
    Environment,
    SignalStatus,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import Strategy as StrategyModel
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS
from loom.trading_pass import expire_stale_signals, refresh_counterfactuals, run_trading_pass


def _seed(session):
    strategy = StrategyModel(
        key="low_vol_compounder",
        name="Low-Vol Compounder",
        style=StrategyStyle.trading,
        approval_mode=ApprovalMode.manual,
    )
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params=dict(DEFAULT_PARAMS)
    )
    session.add(config)
    session.commit()
    return strategy


def test_stale_pending_signals_expire_and_get_a_counterfactual(session):
    _seed(session)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )
    signal = signals[0]
    assert signal.status == SignalStatus.pending_approval

    expired = expire_stale_signals(
        session, Environment.demo, source, max_age_hours=1, now=datetime.utcnow() + timedelta(hours=2)
    )

    assert signal.id in {s.id for s in expired}
    assert signal.status == SignalStatus.expired
    assert signal.counterfactual_outcome is not None


def test_fresh_pending_signals_are_not_expired(session):
    _seed(session)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )
    signal = signals[0]

    expired = expire_stale_signals(session, Environment.demo, source, max_age_hours=24)

    assert expired == []
    assert signal.status == SignalStatus.pending_approval


def test_refresh_counterfactuals_updates_still_open_outcomes(session):
    _seed(session)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )
    signal = signals[0]
    signal.status = SignalStatus.rejected
    signal.counterfactual_outcome = {"status": "still-open", "exit_date": None, "exit_price": 1.0, "return_pct": 0.0}
    session.commit()

    updated = refresh_counterfactuals(session, Environment.demo, source)

    assert updated == 1
    assert signal.counterfactual_outcome is not None


def test_refresh_counterfactuals_skips_already_resolved(session):
    _seed(session)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )
    signal = signals[0]
    signal.status = SignalStatus.rejected
    signal.counterfactual_outcome = {
        "status": "hit-target",
        "exit_date": "2023-08-02",
        "exit_price": 999,
        "return_pct": 0.1,
    }
    session.commit()

    updated = refresh_counterfactuals(session, Environment.demo, source)

    assert updated == 0
    assert signal.counterfactual_outcome["exit_price"] == 999
