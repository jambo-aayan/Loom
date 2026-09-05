from sqlalchemy.orm import Session

from loom.insight.generator import InsightGenerator
from loom.models import Insight, InsightTier, Signal


def generate_screening_insight(session: Session, signal: Signal, generator: InsightGenerator) -> Insight:
    content = generator.generate_screening(signal)
    insight = Insight(signal_id=signal.id, tier=InsightTier.screening, content=content)
    session.add(insight)
    session.commit()
    return insight
