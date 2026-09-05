from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.insight.generator import InsightGenerator
from loom.models import Environment, Insight, InsightTier, Signal


def generate_screening_insight(session: Session, signal: Signal, generator: InsightGenerator) -> Insight:
    content = generator.generate_screening(signal)
    insight = Insight(signal_id=signal.id, tier=InsightTier.screening, content=content)
    session.add(insight)
    session.commit()
    return insight


def run_screening_job(
    session: Session, generator: InsightGenerator, environment: Environment | None = None
) -> list[Insight]:
    """The screening-tier Insight job (story 30, 52, 54): runs on every signal candidate that
    doesn't have one yet, as its own job separate from the trading pass — invoke on its own
    schedule (`loom screen-insights`), not inline within `run_trading_pass`, so slower/costlier
    LLM calls never block or delay order-related, rate-limit-sensitive operations."""
    query = select(Signal)
    if environment is not None:
        query = query.where(Signal.environment == environment)
    candidates = session.execute(query).scalars().all()

    already_screened = {
        row[0]
        for row in session.execute(
            select(Insight.signal_id).where(Insight.tier == InsightTier.screening)
        ).all()
    }

    created = [
        generate_screening_insight(session, signal, generator)
        for signal in candidates
        if signal.id not in already_screened
    ]
    return created
