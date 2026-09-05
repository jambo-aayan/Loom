"""Volatility Harvester (ADR-0009 #2): buy on a pullback vs. an asset's own recent range, trim
on a bounce back toward the mean, optionally add on further weakness (bounded by a max position
size). Data: daily OHLC, a z-score vs. a rolling mean, the position's own cost basis.

The add-on-weakness action is always `pending-approval`, regardless of confidence or the
strategy's configured Approval mode (story 22) — it's the one action in the v1 roster where
being confidently wrong compounds fastest, so it's flagged via
`ProposedSignal.requires_manual_approval_override`, which `trading_pass._decide_approval`
always honors ahead of the strategy's own Approval mode.
"""

from __future__ import annotations

import statistics

from loom.strategy import (
    AccountState,
    ExitPlan,
    MarketData,
    ProposedSignal,
    Strategy,
    StrategyConfig,
)

DEFAULT_PARAMS = {
    "window": 20,
    "entry_z_score": -1.5,  # buy when price is this many std-devs below its rolling mean
    "add_on_weakness_z_score": -2.5,  # deeper pullback that triggers an (always-manual) add
    "exit_z_score": -0.2,  # trim once price has bounced back most of the way to the mean
    "max_add_ons": 1,
    "profit_target_pct": 0.06,
    "stop_loss_pct": 0.05,
    "time_exit_days": 20,
    "position_cash_fraction": 0.08,
}


def _z_score(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    recent = closes[-window:]
    mean = statistics.fmean(recent)
    stdev = statistics.pstdev(recent)
    if stdev == 0:
        return None
    return (closes[-1] - mean) / stdev


class VolatilityHarvester(Strategy):
    key = "volatility_harvester"
    style = "trading"

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config or StrategyConfig(params=dict(DEFAULT_PARAMS)))

    def generate_signals(
        self, market_data: MarketData, positions: AccountState, account: AccountState
    ) -> list[ProposedSignal]:
        p = {**DEFAULT_PARAMS, **self.config.params}
        window = int(p["window"])
        signals: list[ProposedSignal] = []

        for instrument, history in market_data.histories.items():
            if len(history.bars) < window:
                continue
            closes = [b.close for b in history.bars]
            z = _z_score(closes, window)
            if z is None:
                continue
            latest_price = history.bars[-1].close
            position = account.position_in(instrument)

            if position is None:
                if z <= p["entry_z_score"]:
                    signals.append(_entry_signal(instrument, latest_price, z, p, account))
                continue

            change_pct = (latest_price - position.average_price) / position.average_price
            if z >= p["exit_z_score"] or change_pct >= p["profit_target_pct"] or change_pct <= -p["stop_loss_pct"]:
                signals.append(_exit_signal(instrument, latest_price, "mean reversion / exit plan"))
            elif z <= p["add_on_weakness_z_score"] and position.add_count - 1 < p["max_add_ons"]:
                # add_count includes the opening buy, so "adds so far" is add_count - 1 —
                # bounded by max_add_ons (story 22's "bounded by a max position size").
                signals.append(_add_on_weakness_signal(instrument, latest_price, z, p, account))

        return signals


def _entry_signal(instrument: str, price: float, z: float, p: dict, account: AccountState) -> ProposedSignal:
    # Confidence calibration from backtested win-rate buckets is M2·V5 (#36); this is the
    # deterministic placeholder every strategy carries until that ticket replaces it — a deeper
    # pullback (more negative z) is treated as a stronger, more confident setup.
    confidence = max(0.0, min(1.0, 0.5 + abs(z - p["entry_z_score"]) / 4))
    return ProposedSignal(
        instrument=instrument,
        signal_type="entry",
        action="buy",
        confidence=round(confidence, 4),
        exit_plan=ExitPlan(
            profit_target_pct=p["profit_target_pct"],
            stop_loss_pct=p["stop_loss_pct"],
            time_exit_days=p["time_exit_days"],
        ),
        reference_price=price,
        quantity_hint=(account.cash * p["position_cash_fraction"]) / price,
        strength=abs(z - p["entry_z_score"]),
        reasoning=f"{instrument}: {window_desc(z)} pullback below its {p['window']}d mean (z={z:.2f}).",
    )


def _add_on_weakness_signal(instrument: str, price: float, z: float, p: dict, account: AccountState) -> ProposedSignal:
    return ProposedSignal(
        instrument=instrument,
        signal_type="entry",
        action="add",
        confidence=round(max(0.0, min(1.0, 0.5 + abs(z - p["add_on_weakness_z_score"]) / 4)), 4),
        exit_plan=ExitPlan(
            profit_target_pct=p["profit_target_pct"],
            stop_loss_pct=p["stop_loss_pct"],
            time_exit_days=p["time_exit_days"],
        ),
        reference_price=price,
        quantity_hint=(account.cash * p["position_cash_fraction"] / 2) / price,
        strength=abs(z - p["add_on_weakness_z_score"]),
        requires_manual_approval_override=True,
        reasoning=(
            f"{instrument}: further weakness (z={z:.2f}) past the add-on threshold — "
            "always requires manual approval, regardless of confidence or Approval mode."
        ),
    )


def _exit_signal(instrument: str, price: float, reason: str) -> ProposedSignal:
    return ProposedSignal(
        instrument=instrument,
        signal_type="exit",
        action="sell",
        confidence=0.95,
        exit_plan=ExitPlan(),
        reference_price=price,
        reasoning=f"{instrument}: {reason} at {price:.2f}.",
    )


def window_desc(z: float) -> str:
    return "sharp" if z < -2 else "moderate"
