"""Risk/sizing layer: every signal is checked against configurable limits before it can become
an order (story 24). Used identically by live/demo trading (loom.trading_pass) and by the
backtest engine (loom.backtest.engine), so a backtest reflects real constraints (story 45)."""

from __future__ import annotations

from dataclasses import dataclass

from loom.strategy import AccountState, ProposedSignal


@dataclass(frozen=True)
class RiskLimits:
    max_position_size_pct: float = 0.15  # fraction of account value in a single instrument
    max_total_exposure_pct: float = 0.9  # fraction of account value invested at once
    daily_loss_limit_pct: float = 0.05  # fraction of account value lost in a day -> kill switch


@dataclass(frozen=True)
class SizedOrder:
    instrument: str
    action: str
    quantity: float
    reference_price: float


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    sized_order: SizedOrder | None = None


def size_and_check(
    signal: ProposedSignal,
    account: AccountState,
    account_value: float,
    limits: RiskLimits,
) -> RiskDecision:
    """Volatility Harvester's "add to a losing position" action is exempt from auto-approval
    regardless of mode (story 22) — enforced by the caller via `requires_manual_approval_override`
    on the signal, not here; this function only decides whether the trade is allowed at all and
    how big it can be."""

    if signal.action == "sell":
        position = account.position_in(signal.instrument)
        quantity = position.quantity if position else signal.quantity_hint
        return RiskDecision(
            approved=True,
            reason="exit orders are always allowed through risk/sizing",
            sized_order=SizedOrder(signal.instrument, "sell", quantity, signal.reference_price),
        )

    max_position_value = account_value * limits.max_position_size_pct
    requested_value = signal.quantity_hint * signal.reference_price
    position_value = min(requested_value, max_position_value)

    invested_value = sum(p.quantity * signal.reference_price for p in account.positions)
    exposure_after = invested_value + position_value
    max_exposure_value = account_value * limits.max_total_exposure_pct
    if exposure_after > max_exposure_value:
        headroom = max(0.0, max_exposure_value - invested_value)
        position_value = min(position_value, headroom)

    if position_value <= 0 or account.cash < position_value:
        return RiskDecision(approved=False, reason="insufficient cash or exposure headroom")

    quantity = position_value / signal.reference_price
    return RiskDecision(
        approved=True,
        reason="within position size and exposure limits",
        sized_order=SizedOrder(signal.instrument, signal.action, quantity, signal.reference_price),
    )


def daily_loss_breached(account_value_start_of_day: float, account_value_now: float, limits: RiskLimits) -> bool:
    if account_value_start_of_day <= 0:
        return False
    loss_pct = (account_value_start_of_day - account_value_now) / account_value_start_of_day
    return loss_pct >= limits.daily_loss_limit_pct
