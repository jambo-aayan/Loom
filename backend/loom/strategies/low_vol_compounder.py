"""Low-Vol Compounder (ADR-0009 #1): buy low-volatility, large-cap/index holdings, hold for
small, consistent gains. Data: daily OHLC, realized volatility (rolling stdev of returns)."""

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
    "volatility_window": 20,
    "volatility_threshold": 0.015,  # max acceptable daily-return stdev
    "trend_window": 50,
    "profit_target_pct": 0.04,
    "stop_loss_pct": 0.02,
    "time_exit_days": 30,
    "position_cash_fraction": 0.1,
}


def _daily_returns(closes: list[float]) -> list[float]:
    return [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] != 0
    ]


class LowVolCompounder(Strategy):
    key = "low_vol_compounder"
    style = "trading"

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config or StrategyConfig(params=dict(DEFAULT_PARAMS)))

    def generate_signals(
        self, market_data: MarketData, positions: AccountState, account: AccountState
    ) -> list[ProposedSignal]:
        p = {**DEFAULT_PARAMS, **self.config.params}
        vol_window = int(p["volatility_window"])
        trend_window = int(p["trend_window"])
        signals: list[ProposedSignal] = []

        for instrument, history in market_data.histories.items():
            bars = history.bars
            if len(bars) < max(vol_window, trend_window) + 1:
                continue
            if account.position_in(instrument) is not None:
                continue  # already held; Compounder doesn't average up/down in v1

            closes = [b.close for b in bars]
            recent_closes = closes[-vol_window - 1 :]
            returns = _daily_returns(recent_closes)
            if len(returns) < 2:
                continue
            realized_vol = statistics.pstdev(returns)

            trend_avg = sum(closes[-trend_window:]) / trend_window
            latest = bars[-1]

            is_low_vol = realized_vol <= p["volatility_threshold"]
            is_above_trend = latest.close >= trend_avg

            if not (is_low_vol and is_above_trend):
                continue

            # Confidence: how comfortably volatility clears the threshold, calibration is M2
            # scope (story 20, ticket #36) — this is a simple, deterministic heuristic for M1.
            headroom = (p["volatility_threshold"] - realized_vol) / p["volatility_threshold"]
            confidence = max(0.0, min(1.0, 0.5 + headroom))

            signals.append(
                ProposedSignal(
                    instrument=instrument,
                    signal_type="entry",
                    action="buy",
                    confidence=round(confidence, 4),
                    exit_plan=ExitPlan(
                        profit_target_pct=p["profit_target_pct"],
                        stop_loss_pct=p["stop_loss_pct"],
                        time_exit_days=p["time_exit_days"],
                    ),
                    reference_price=latest.close,
                    quantity_hint=(account.cash * p["position_cash_fraction"]) / latest.close,
                    reasoning=(
                        f"{instrument}: {vol_window}d realized volatility {realized_vol:.4f} is "
                        f"below the {p['volatility_threshold']:.4f} threshold and price is at or "
                        f"above its {trend_window}d average — a low-volatility uptrend."
                    ),
                )
            )

        for position in account.positions:
            pos_history = market_data.get(position.instrument)
            if pos_history is None or pos_history.latest is None:
                continue
            latest_price = pos_history.latest.close
            change_pct = (latest_price - position.average_price) / position.average_price
            if change_pct >= p["profit_target_pct"]:
                signals.append(_exit_signal(position.instrument, "profit target", latest_price, 0.95))
            elif change_pct <= -p["stop_loss_pct"]:
                signals.append(_exit_signal(position.instrument, "stop loss", latest_price, 0.95))

        return signals


def _exit_signal(instrument: str, reason: str, price: float, confidence: float) -> ProposedSignal:
    # Exit-type signals realizing a pre-calculated target/stop are arithmetic, not forecasts,
    # and read as high-confidence by construction (CONTEXT.md "Confidence").
    return ProposedSignal(
        instrument=instrument,
        signal_type="exit",
        action="sell",
        confidence=confidence,
        exit_plan=ExitPlan(),
        reference_price=price,
        reasoning=f"{instrument}: exiting on {reason} at {price:.2f}.",
    )
