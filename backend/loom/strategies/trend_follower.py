"""Trend Follower (ADR-0009 #3): enter on a moving-average crossover (e.g. 50/200 golden cross)
or an N-day-high breakout; exit on the reverse crossover or a trailing stop. Data: daily OHLC
only.

The "trailing stop" is approximated as a fixed percentage stop from entry price (`exit_plan.
stop_loss_pct`), the same mechanism every other strategy's exit plan uses and the one the shared
backtest engine (`loom.backtest.engine.check_exit`) and live risk layer already know how to
enforce. A true trailing-stop-from-peak-since-entry would need the position's entry date/peak
price, which `PositionSnapshot`/`AccountState` don't carry — a deliberate v1 simplification, not
an oversight; worth revisiting if it turns out to matter empirically. The reverse-crossover exit
is real, not approximated: it's detected directly from price history each pass.
"""

from __future__ import annotations

from loom.strategy import (
    AccountState,
    ExitPlan,
    MarketData,
    ProposedSignal,
    Strategy,
    StrategyConfig,
)

DEFAULT_PARAMS = {
    "short_window": 50,
    "long_window": 200,
    "breakout_window": 20,
    "stop_loss_pct": 0.08,
    "time_exit_days": 180,
    "position_cash_fraction": 0.1,
}


def _sma(closes: list[float], window: int, end: int) -> float | None:
    """Simple moving average of `window` closes ending at index `end` (exclusive of `end`+1...
    i.e. closes[end - window + 1 : end + 1])."""
    if end - window + 1 < 0:
        return None
    return sum(closes[end - window + 1 : end + 1]) / window


def _golden_cross(closes: list[float], short_window: int, long_window: int) -> bool:
    n = len(closes)
    if n < long_window + 1:
        return False
    short_now, long_now = _sma(closes, short_window, n - 1), _sma(closes, long_window, n - 1)
    short_prev, long_prev = _sma(closes, short_window, n - 2), _sma(closes, long_window, n - 2)
    if short_now is None or long_now is None or short_prev is None or long_prev is None:
        return False
    return short_prev <= long_prev and short_now > long_now


def _death_cross(closes: list[float], short_window: int, long_window: int) -> bool:
    n = len(closes)
    if n < long_window + 1:
        return False
    short_now, long_now = _sma(closes, short_window, n - 1), _sma(closes, long_window, n - 1)
    short_prev, long_prev = _sma(closes, short_window, n - 2), _sma(closes, long_window, n - 2)
    if short_now is None or long_now is None or short_prev is None or long_prev is None:
        return False
    return short_prev >= long_prev and short_now < long_now


def _is_n_day_high(closes: list[float], window: int) -> bool:
    if len(closes) < window + 1:
        return False
    return closes[-1] > max(closes[-window - 1 : -1])


class TrendFollower(Strategy):
    key = "trend_follower"
    style = "trading"

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config or StrategyConfig(params=dict(DEFAULT_PARAMS)))

    def generate_signals(
        self, market_data: MarketData, positions: AccountState, account: AccountState
    ) -> list[ProposedSignal]:
        p = {**DEFAULT_PARAMS, **self.config.params}
        short_window, long_window = int(p["short_window"]), int(p["long_window"])
        signals: list[ProposedSignal] = []

        for instrument, history in market_data.histories.items():
            closes = [b.close for b in history.bars]
            if not closes:
                continue
            latest_price = closes[-1]
            position = account.position_in(instrument)

            if position is not None:
                if _death_cross(closes, short_window, long_window):
                    signals.append(
                        ProposedSignal(
                            instrument=instrument,
                            signal_type="exit",
                            action="sell",
                            confidence=0.9,
                            exit_plan=ExitPlan(),
                            reference_price=latest_price,
                            reasoning=f"{instrument}: {short_window}/{long_window}d death cross.",
                        )
                    )
                continue

            golden_cross = _golden_cross(closes, short_window, long_window)
            breakout = _is_n_day_high(closes, int(p["breakout_window"]))
            if not (golden_cross or breakout):
                continue

            trigger = "golden cross" if golden_cross else f"{p['breakout_window']}d high breakout"
            # Confidence calibration (M2·V5, #36) replaces this placeholder from `strength`; a
            # golden cross (trend confirmed by two moving averages) reads slightly more
            # confident than a raw N-day-high breakout on its own, until calibration overrides it.
            confidence = 0.75 if golden_cross else 0.65
            short_ma, long_ma = _sma(closes, short_window, len(closes) - 1), _sma(closes, long_window, len(closes) - 1)
            gap_pct = (short_ma - long_ma) / long_ma if short_ma is not None and long_ma else 0.0
            signals.append(
                ProposedSignal(
                    instrument=instrument,
                    signal_type="entry",
                    action="buy",
                    confidence=confidence,
                    exit_plan=ExitPlan(stop_loss_pct=p["stop_loss_pct"], time_exit_days=p["time_exit_days"]),
                    reference_price=latest_price,
                    quantity_hint=(account.cash * p["position_cash_fraction"]) / latest_price,
                    strength=gap_pct,
                    reasoning=f"{instrument}: entering on {trigger}.",
                )
            )

        return signals
