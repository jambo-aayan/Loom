from loom.insight.generator import FakeInsightGenerator
from loom.insight.screening import generate_screening_insight
from loom.models import (
    Book,
    ConfigVersionStatus,
    Environment,
    InsightTier,
    Signal,
    SignalStatus,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import (
    Strategy as StrategyModel,
)


def test_generate_screening_insight_stores_content(session):
    strategy = StrategyModel(key="low_vol_compounder", name="Low-Vol Compounder", style=StrategyStyle.trading)
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params={}
    )
    book = Book(strategy_id=strategy.id, environment=Environment.demo, name="Compounder · demo")
    session.add_all([config, book])
    session.flush()
    signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument="VUSA.L",
        signal_type="entry",
        action="buy",
        confidence=0.82,
        exit_plan={"profit_target_pct": 0.04, "stop_loss_pct": 0.02, "time_exit_days": 30},
        quantity=10,
        reference_price=75.0,
        status=SignalStatus.pending_approval,
    )
    session.add(signal)
    session.commit()

    insight = generate_screening_insight(session, signal, FakeInsightGenerator())

    assert insight.tier == InsightTier.screening
    assert "VUSA.L" in insight.content
    assert insight.id is not None
    assert signal.insights[0].id == insight.id
