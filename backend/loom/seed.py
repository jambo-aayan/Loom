"""Seeds each v1 strategy (ADR-0009) with a promoted v1 config, if not already present.
Idempotent — safe to call on every startup/CLI invocation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.config_versions import create_draft, promote
from loom.models import Strategy as StrategyModel
from loom.models import StrategyStyle
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS as COMPOUNDER_PARAMS
from loom.strategies.trend_follower import DEFAULT_PARAMS as TREND_FOLLOWER_PARAMS
from loom.strategies.value_quality_dip_buyer import DEFAULT_PARAMS as DIP_BUYER_PARAMS
from loom.strategies.volatility_breakout import DEFAULT_PARAMS as BREAKOUT_PARAMS
from loom.strategies.volatility_harvester import DEFAULT_PARAMS as HARVESTER_PARAMS

_ROSTER = [
    ("low_vol_compounder", "Low-Vol Compounder", StrategyStyle.trading, COMPOUNDER_PARAMS),
    ("volatility_harvester", "Volatility Harvester", StrategyStyle.trading, HARVESTER_PARAMS),
    ("trend_follower", "Trend Follower", StrategyStyle.trading, TREND_FOLLOWER_PARAMS),
    ("volatility_breakout", "Volatility Breakout", StrategyStyle.trading, BREAKOUT_PARAMS),
    ("value_quality_dip_buyer", "Value/Quality Dip-Buyer", StrategyStyle.investment, DIP_BUYER_PARAMS),
]


def _seed_one(session: Session, key: str, name: str, style: StrategyStyle, params: dict) -> StrategyModel:
    strategy = session.execute(select(StrategyModel).where(StrategyModel.key == key)).scalar_one_or_none()
    if strategy is not None:
        return strategy

    strategy = StrategyModel(key=key, name=name, style=style, live_enabled=False)
    session.add(strategy)
    session.flush()
    version = create_draft(session, strategy.id, dict(params), note="Initial v1 parameters")
    promote(session, version)
    return strategy


def seed_low_vol_compounder(session: Session) -> StrategyModel:
    return _seed_one(session, "low_vol_compounder", "Low-Vol Compounder", StrategyStyle.trading, DEFAULT_PARAMS)


def seed_all_strategies(session: Session) -> list[StrategyModel]:
    return [_seed_one(session, key, name, style, params) for key, name, style, params in _ROSTER]
