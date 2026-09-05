from loom import strategies  # noqa: F401
from loom.execution.broker import FakeBrokerClient
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import ApprovalMode, ConfigVersionStatus, Environment, StrategyConfigVersion, StrategyStyle
from loom.models import Strategy as StrategyModel
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS
from loom.trading_pass import reject_signal, run_trading_pass


def test_rejecting_a_signal_attaches_a_counterfactual_outcome(session):
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

    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )
    signal = signals[0]
    assert signal.counterfactual_outcome is None

    reject_signal(session, signal, note="not now", market_data_source=source)

    assert signal.counterfactual_outcome is not None
    assert signal.counterfactual_outcome["status"] in {"hit-target", "hit-stop", "time-exit", "still-open"}
