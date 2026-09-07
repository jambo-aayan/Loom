from sqlalchemy import select

from loom.insight.generator import FakeInsightGenerator
from loom.insight.research import generate_research_insight, is_research_eligible, run_research_job
from loom.models import (
    ApprovalMode,
    Book,
    ConfigVersionStatus,
    Environment,
    Insight,
    InsightTier,
    Signal,
    SignalStatus,
    SignalType,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import Strategy as StrategyModel


def _seed_signal(session, style, status, key="value_quality_dip_buyer"):
    strategy = StrategyModel(key=key, name=key, style=style, approval_mode=ApprovalMode.manual)
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params={}
    )
    book = Book(strategy_id=strategy.id, environment=Environment.demo, name=f"{key} · demo")
    session.add_all([config, book])
    session.flush()
    signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument="VUSA.L",
        signal_type=SignalType.entry,
        action="buy",
        confidence=0.9,
        exit_plan={"profit_target_pct": None, "stop_loss_pct": None, "time_exit_days": None},
        quantity=10,
        reference_price=100.0,
        status=status,
    )
    session.add(signal)
    session.commit()
    return signal


def test_investment_style_pending_signal_is_eligible(session):
    signal = _seed_signal(session, StrategyStyle.investment, SignalStatus.pending_approval)
    assert is_research_eligible(signal) is True


def test_trading_style_signal_is_never_eligible_regardless_of_status(session):
    for status in (SignalStatus.pending_approval, SignalStatus.auto_approved, SignalStatus.proposed):
        signal = _seed_signal(session, StrategyStyle.trading, status, key=f"trading-{status.value}")
        assert is_research_eligible(signal) is False


def test_investment_style_signal_not_yet_decided_is_not_eligible(session):
    signal = _seed_signal(session, StrategyStyle.investment, SignalStatus.proposed)
    assert is_research_eligible(signal) is False


def test_investment_style_rejected_signal_is_not_eligible(session):
    signal = _seed_signal(session, StrategyStyle.investment, SignalStatus.rejected)
    assert is_research_eligible(signal) is False


def test_generate_research_insight_persists_a_research_tier_insight(session):
    signal = _seed_signal(session, StrategyStyle.investment, SignalStatus.pending_approval)

    insight = generate_research_insight(session, signal, FakeInsightGenerator())

    assert insight.tier == InsightTier.research
    assert insight.signal_id == signal.id
    assert signal.instrument in insight.content


def test_research_content_has_a_thesis_and_key_risks_shape_distinct_from_screening(session):
    """Research commentary must actually look like a thesis, not just screening's one-line
    "why this fired" text with a different tier label (ADR-0013: "a written thesis")."""
    signal = _seed_signal(session, StrategyStyle.investment, SignalStatus.pending_approval)
    generator = FakeInsightGenerator()

    research = generate_research_insight(session, signal, generator)
    screening_content = generator.generate_screening(signal)

    assert "Thesis:" in research.content
    assert "Key risks:" in research.content
    assert research.content != screening_content


def test_run_research_job_only_processes_eligible_signals(session):
    eligible = _seed_signal(session, StrategyStyle.investment, SignalStatus.pending_approval, key="dip-buyer")
    ineligible_style = _seed_signal(session, StrategyStyle.trading, SignalStatus.pending_approval, key="compounder")
    ineligible_status = _seed_signal(session, StrategyStyle.investment, SignalStatus.proposed, key="dip-buyer-2")

    created = run_research_job(session, FakeInsightGenerator(), environment=Environment.demo)

    assert len(created) == 1
    assert created[0].signal_id == eligible.id
    processed_ids = {i.signal_id for i in created}
    assert ineligible_style.id not in processed_ids
    assert ineligible_status.id not in processed_ids


def test_run_research_job_does_not_reprocess_an_already_researched_signal(session):
    _seed_signal(session, StrategyStyle.investment, SignalStatus.pending_approval)
    generator = FakeInsightGenerator()

    first = run_research_job(session, generator, environment=Environment.demo)
    second = run_research_job(session, generator, environment=Environment.demo)

    assert len(first) == 1
    assert len(second) == 0
    all_research = session.execute(select(Insight).where(Insight.tier == InsightTier.research)).scalars().all()
    assert len(all_research) == 1
