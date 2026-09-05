"""Registers every concrete Strategy implementation with loom.trading_pass.STRATEGY_REGISTRY."""

from loom.strategies.low_vol_compounder import LowVolCompounder
from loom.trading_pass import register_strategy

register_strategy(LowVolCompounder)

ALL_STRATEGIES = [LowVolCompounder]
