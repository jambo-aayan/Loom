"""The deeper research tier (story 37/51 origin, ADR-0009, ADR-0013, ticket #48). Hard-gated by
`Strategy.style`: only `investment`-style signals are ever eligible — `trading`-style strategies
never get more than screening, permanently, regardless of confidence or which path invokes this.

Two invocation paths share `is_research_eligible` but nothing else: `run_research_job` is the
automatic, free-tier (Gemini) sweep, mirroring `run_screening_job`'s shape as its own job, never
inline in the trading pass; the manual, paid (Sonnet) path lives entirely in
`loom.api.routers.insights`'s `POST /signals/{id}/research` endpoint — that endpoint is the ONLY
caller of the paid generator anywhere in the codebase (ADR-0013: never scheduled, never batched,
never a side effect of anything else)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.insight.generator import InsightGenerator
from loom.models import Environment, Insight, InsightTier, Signal, SignalStatus, StrategyStyle

_ELIGIBLE_STATUSES = (SignalStatus.pending_approval, SignalStatus.auto_approved)


def is_research_eligible(signal: Signal) -> bool:
    strategy = signal.strategy
    if strategy is None or strategy.style != StrategyStyle.investment:
        return False
    return signal.status in _ELIGIBLE_STATUSES


def generate_research_insight(session: Session, signal: Signal, generator: InsightGenerator) -> Insight:
    content = generator.generate_research(signal)
    insight = Insight(signal_id=signal.id, tier=InsightTier.research, content=content)
    session.add(insight)
    session.commit()
    return insight


def run_research_job(
    session: Session, generator: InsightGenerator, environment: Environment | None = None
) -> list[Insight]:
    """The automatic, free-tier research pass — its own job, run on its own schedule
    (`loom research-insights`), same reasoning as `run_screening_job`: a slower/costlier LLM
    call should never block or delay order-related, rate-limit-sensitive work."""
    query = select(Signal)
    if environment is not None:
        query = query.where(Signal.environment == environment)
    candidates = session.execute(query).scalars().all()

    already_researched = {
        row[0] for row in session.execute(select(Insight.signal_id).where(Insight.tier == InsightTier.research)).all()
    }

    return [
        generate_research_insight(session, signal, generator)
        for signal in candidates
        if signal.id not in already_researched and is_research_eligible(signal)
    ]
