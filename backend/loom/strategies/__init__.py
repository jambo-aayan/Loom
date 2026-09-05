"""Registers every concrete Strategy implementation with loom.trading_pass.STRATEGY_REGISTRY."""

from loom.strategies.low_vol_compounder import LowVolCompounder
from loom.strategies.trend_follower import TrendFollower
from loom.strategies.value_quality_dip_buyer import ValueQualityDipBuyer
from loom.strategies.volatility_breakout import VolatilityBreakout
from loom.strategies.volatility_harvester import VolatilityHarvester
from loom.trading_pass import register_strategy

ALL_STRATEGIES = [
    LowVolCompounder,
    VolatilityHarvester,
    TrendFollower,
    VolatilityBreakout,
    ValueQualityDipBuyer,
]

# Explicit calls rather than a loop over ALL_STRATEGIES: looping widens each element's static
# type to the shared (abstract) Strategy base, which mypy's type-abstract check then (correctly
# cautiously) refuses to pass to register_strategy's type[Strategy] parameter.
register_strategy(LowVolCompounder)
register_strategy(VolatilityHarvester)
register_strategy(TrendFollower)
register_strategy(VolatilityBreakout)
register_strategy(ValueQualityDipBuyer)
