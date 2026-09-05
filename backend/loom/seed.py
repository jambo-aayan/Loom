"""Seeds the Low-Vol Compounder strategy with a promoted v1 config, if not already present.
Idempotent — safe to call on every startup/CLI invocation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.config_versions import create_draft, promote
from loom.models import Strategy as StrategyModel
from loom.models import StrategyStyle
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS


def seed_low_vol_compounder(session: Session) -> StrategyModel:
    strategy = session.execute(
        select(StrategyModel).where(StrategyModel.key == "low_vol_compounder")
    ).scalar_one_or_none()
    if strategy is not None:
        return strategy

    strategy = StrategyModel(
        key="low_vol_compounder",
        name="Low-Vol Compounder",
        style=StrategyStyle.trading,
        live_enabled=False,
    )
    session.add(strategy)
    session.flush()
    version = create_draft(session, strategy.id, dict(DEFAULT_PARAMS), note="Initial v1 parameters")
    promote(session, version)
    return strategy
