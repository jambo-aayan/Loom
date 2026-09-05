"""The pluggable Strategy interface every strategy implements (story 14, ADR-0009).

`generate_signals(market_data, positions, account) -> list[ProposedSignal]`. Deterministic given
fixed inputs, always emits a confidence score and an exit plan, and never mutates external state
directly (Testing Decisions, issue #1) — the strategy contract test suite in
tests/test_strategy_contract.py runs every concrete strategy against these rules.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Bar:
    date: str  # ISO date, "YYYY-MM-DD"
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class InstrumentHistory:
    """Bars up to (and including) the simulated "now" — never beyond it (no-lookahead rule,
    enforced by the backtest engine's fake clock, not by the strategy itself)."""

    instrument: str
    bars: tuple[Bar, ...]

    @property
    def latest(self) -> Bar | None:
        return self.bars[-1] if self.bars else None


@dataclass(frozen=True)
class MarketData:
    histories: dict[str, InstrumentHistory]

    def get(self, instrument: str) -> InstrumentHistory | None:
        return self.histories.get(instrument)


@dataclass(frozen=True)
class PositionSnapshot:
    instrument: str
    quantity: float
    average_price: float
    book_id: str


@dataclass(frozen=True)
class AccountState:
    cash: float
    positions: tuple[PositionSnapshot, ...] = ()

    def position_in(self, instrument: str) -> PositionSnapshot | None:
        return next((p for p in self.positions if p.instrument == instrument), None)


@dataclass(frozen=True)
class ExitPlan:
    profit_target_pct: float | None = None
    stop_loss_pct: float | None = None
    time_exit_days: int | None = None

    def as_dict(self) -> dict:
        return {
            "profit_target_pct": self.profit_target_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "time_exit_days": self.time_exit_days,
        }


@dataclass(frozen=True)
class ProposedSignal:
    instrument: str
    signal_type: str  # "entry" | "exit"
    action: str  # "buy" | "sell" | "add"
    confidence: float  # 0.0-1.0; a placeholder for entry signals until confidence calibration
    # (#36) overrides it from backtested win-rate buckets — see loom.calibration. Exit signals
    # keep this value as-is; it's arithmetic-confidence-by-construction, not a forecast.
    exit_plan: ExitPlan
    reference_price: float
    quantity_hint: float = 0.0
    requires_manual_approval_override: bool | None = None
    reasoning: str = ""
    # A raw, strategy-specific "how strong is this entry setup" number (e.g. z-score distance
    # past threshold, price-dip percentage) — the input `loom.calibration` buckets by, per
    # strategy, to replace `confidence` with a realized win rate. None for exit signals, which
    # aren't calibrated (story 21: exit-type signals stay high-confidence by construction).
    strength: float | None = None


@dataclass(frozen=True)
class StrategyConfig:
    params: dict = field(default_factory=dict)


class Strategy(ABC):
    key: str
    style: str  # "trading" | "investment"

    def __init__(self, config: StrategyConfig):
        self.config = config

    @classmethod
    def from_config(cls, params: dict) -> Strategy:
        """The uniform construction path every call site (trading_pass, backtest CLI/API) uses:
        `STRATEGY_REGISTRY[key].from_config(config_version.params)`. Every strategy works with
        just this; a strategy needing an extra collaborator (e.g. Dip-Buyer's fundamentals
        provider) overrides this rather than forcing a special case into the generic call sites."""
        return cls(StrategyConfig(params=params))

    @abstractmethod
    def generate_signals(
        self, market_data: MarketData, positions: AccountState, account: AccountState
    ) -> list[ProposedSignal]:
        """Pure function of its inputs: same inputs -> same signals. Must never mutate
        market_data, positions, or account."""
        raise NotImplementedError
