from loom import strategies  # noqa: F401
from loom.execution.broker import FakeBrokerClient
from loom.insight.generator import FakeInsightGenerator
from loom.insight.screening import generate_screening_insight, run_screening_job
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import ApprovalMode, ConfigVersionStatus, Environment, StrategyConfigVersion, StrategyStyle
from loom.models import Strategy as StrategyModel
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS
from loom.trading_pass import run_trading_pass


def _seed_and_generate_signals(session):
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
    return run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )


def test_screening_job_covers_every_candidate_without_one_yet(session):
    signals = _seed_and_generate_signals(session)
    assert len(signals) >= 1

    created = run_screening_job(session, FakeInsightGenerator(), environment=Environment.demo)

    assert len(created) == len(signals)
    assert {c.signal_id for c in created} == {s.id for s in signals}


def test_screening_job_skips_signals_already_screened(session):
    signals = _seed_and_generate_signals(session)
    generate_screening_insight(session, signals[0], FakeInsightGenerator())

    created = run_screening_job(session, FakeInsightGenerator(), environment=Environment.demo)

    assert signals[0].id not in {c.signal_id for c in created}
    assert len(created) == len(signals) - 1


def test_screening_job_is_separate_from_the_trading_pass(session):
    """Running a trading pass alone must not itself create Insights (story 30, 52: the job is
    deliberately separate so a slow LLM call never blocks order-related work)."""
    from loom.models import Insight

    _seed_and_generate_signals(session)

    assert session.query(Insight).count() == 0
