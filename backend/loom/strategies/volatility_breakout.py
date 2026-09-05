"""Volatility Breakout (ADR-0009 #4): flag a multi-month low in Bollinger Band width (a
volatility squeeze), enter on the first confirmed close outside the bands, exit on volatility
normalization or a trailing stop (approximated as a fixed stop_loss_pct — see the note in
strategies/trend_follower.py, the same simplification applies here). Data: daily OHLC, Bollinger
Bands.
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
    "band_window": 20,
    "band_k": 2.0,
    "squeeze_lookback": 60,  # "multi-month" low in band width, in trading days
    "normalization_multiple": 1.6,  # exit once band width expands back to this multiple of the squeeze low
    "stop_loss_pct": 0.06,
    "time_exit_days": 45,
    "position_cash_fraction": 0.08,
}


def _bollinger(closes: list[float], window: int, k: float, end: int) -> tuple[float, float, float] | None:
    """(middle, upper, lower) as of index `end`, or None if not enough history."""
    if end - window + 1 < 0:
        return None
    window_closes = closes[end - window + 1 : end + 1]
    middle = statistics.fmean(window_closes)
    stdev = statistics.pstdev(window_closes)
    return middle, middle + k * stdev, middle - k * stdev


def _band_width_series(closes: list[float], window: int, k: float, lookback: int) -> list[float]:
    n = len(closes)
    widths = []
    for end in range(max(0, n - lookback), n):
        bands = _bollinger(closes, window, k, end)
        if bands is None:
            continue
        middle, upper, lower = bands
        if middle:
            widths.append((upper - lower) / middle)
    return widths


class VolatilityBreakout(Strategy):
    key = "volatility_breakout"
    style = "trading"

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config or StrategyConfig(params=dict(DEFAULT_PARAMS)))

    def generate_signals(
        self, market_data: MarketData, positions: AccountState, account: AccountState
    ) -> list[ProposedSignal]:
        p = {**DEFAULT_PARAMS, **self.config.params}
        window, k = int(p["band_window"]), float(p["band_k"])
        squeeze_lookback = int(p["squeeze_lookback"])
        signals: list[ProposedSignal] = []

        for instrument, history in market_data.histories.items():
            closes = [b.close for b in history.bars]
            n = len(closes)
            if n < window + 2:
                continue
            latest_price = closes[-1]
            position = account.position_in(instrument)

            widths = _band_width_series(closes, window, k, squeeze_lookback)
            if not widths:
                continue
            current_width = widths[-1]
            squeeze_low = min(widths)

            if position is not None:
                # Volatility normalization: band width has expanded back well past its squeeze low
                # (a squeeze_low of exactly 0 — a literally flat band — still normalizes on any
                # subsequent expansion).
                if current_width >= squeeze_low * p["normalization_multiple"] and current_width > squeeze_low:
                    signals.append(
                        ProposedSignal(
                            instrument=instrument,
                            signal_type="exit",
                            action="sell",
                            confidence=0.85,
                            exit_plan=ExitPlan(),
                            reference_price=latest_price,
                            reasoning=f"{instrument}: volatility normalized (band width {current_width:.4f}).",
                        )
                    )
                continue

            # A squeeze was in effect the bar before this one — meaning band width was both near
            # this lookback's low *and* meaningfully tighter than the lookback's typical width,
            # not just incidentally the smallest value in an otherwise-uniformly-choppy series —
            # and today's close breaks out above *that* prior upper band, computed from data up
            # to yesterday so today's own outlier close can't drag the band up to meet it.
            prev_width = widths[-2] if len(widths) > 1 else widths[-1]
            mean_width = statistics.fmean(widths)
            was_squeezed = prev_width <= squeeze_low * 1.05 and prev_width <= mean_width * 0.5
            prev_bands = _bollinger(closes, window, k, n - 2)
            if prev_bands is None or not was_squeezed:
                continue
            _, prev_upper, _ = prev_bands
            if latest_price <= prev_upper:
                continue

            # Confidence calibration (M2·V5, #36) replaces this placeholder; a tighter squeeze
            # relative to its own low reads as a stronger setup for now.
            confidence = round(max(0.0, min(1.0, 0.6 + (squeeze_low / current_width if current_width else 0))), 4)
            signals.append(
                ProposedSignal(
                    instrument=instrument,
                    signal_type="entry",
                    action="buy",
                    confidence=confidence,
                    exit_plan=ExitPlan(stop_loss_pct=p["stop_loss_pct"], time_exit_days=p["time_exit_days"]),
                    reference_price=latest_price,
                    quantity_hint=(account.cash * p["position_cash_fraction"]) / latest_price,
                    strength=(latest_price - prev_upper) / prev_upper,
                    reasoning=(
                        f"{instrument}: confirmed close {latest_price:.2f} outside the upper band "
                        f"{prev_upper:.2f} after a volatility squeeze."
                    ),
                )
            )

        return signals
