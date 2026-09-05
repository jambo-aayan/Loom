"""Value/Quality Dip-Buyer (ADR-0009 #5): screen for P/E meaningfully below the instrument's own
N-year average, a dividend-yield floor, and a basic quality filter (positive earnings, reasonable
debt/equity); holds longer than the Harvester, closer to the Compounder's horizon. The first
strategy driven by fundamentals rather than price data alone.

**Known v1 simplification**: a genuine multi-year historical P/E time series isn't cheaply
available from yfinance's free `info` payload (it would need historical net income, share count,
and price reconstructed and cross-referenced — real scope, not a v1 tracer-bullet concern). This
implementation gates on the instrument's *current* P/E against a fixed ceiling (a reasonable
"meaningfully below normal" proxy) and uses the instrument's own long-run price average — the
same "how far below its own baseline" idea the ADR describes, applied to price, which the data
actually supports — for the entry-timing "dip" itself. Worth revisiting if/when historical
fundamentals become worth the extra integration cost (see BACKLOG.md).
"""

from __future__ import annotations

from loom.fundamentals import FixtureFundamentalsProvider, FundamentalsProvider
from loom.strategy import (
    AccountState,
    ExitPlan,
    MarketData,
    ProposedSignal,
    Strategy,
    StrategyConfig,
)

DEFAULT_PARAMS = {
    "pe_ceiling": 25.0,
    "dividend_yield_floor": 0.015,
    "debt_to_equity_ceiling": 60.0,
    "price_avg_window": 200,
    "dip_threshold_pct": 0.08,
    "profit_target_pct": 0.10,
    "stop_loss_pct": 0.06,
    "time_exit_days": 60,
    "position_cash_fraction": 0.1,
}


def _passes_quality_gate(fundamentals: dict, p: dict) -> bool:
    pe, div_yield, debt_equity = (
        fundamentals.get("pe_ratio"),
        fundamentals.get("dividend_yield"),
        fundamentals.get("debt_to_equity"),
    )
    if pe is None or div_yield is None or debt_equity is None:
        return False  # missing fundamentals are treated conservatively: skip, don't guess
    return (
        0 < pe <= p["pe_ceiling"]
        and div_yield >= p["dividend_yield_floor"]
        and debt_equity <= p["debt_to_equity_ceiling"]
    )


class ValueQualityDipBuyer(Strategy):
    key = "value_quality_dip_buyer"
    style = "investment"

    def __init__(
        self,
        config: StrategyConfig | None = None,
        fundamentals_provider: FundamentalsProvider | None = None,
    ):
        super().__init__(config or StrategyConfig(params=dict(DEFAULT_PARAMS)))
        # Offline/deterministic by default (matches every other external boundary in this app);
        # `from_config` — the path every real call site uses — wires the real yfinance source in.
        self.fundamentals_provider = fundamentals_provider or FixtureFundamentalsProvider()

    @classmethod
    def from_config(cls, params: dict) -> ValueQualityDipBuyer:
        from loom.market_data.yfinance_source import YFinanceSource

        return cls(StrategyConfig(params=params), fundamentals_provider=YFinanceSource())

    def generate_signals(
        self, market_data: MarketData, positions: AccountState, account: AccountState
    ) -> list[ProposedSignal]:
        p = {**DEFAULT_PARAMS, **self.config.params}
        window = int(p["price_avg_window"])
        signals: list[ProposedSignal] = []

        for instrument, history in market_data.histories.items():
            closes = [b.close for b in history.bars]
            if len(closes) < window:
                continue
            latest_price = closes[-1]
            position = account.position_in(instrument)

            if position is not None:
                change_pct = (latest_price - position.average_price) / position.average_price
                if change_pct >= p["profit_target_pct"] or change_pct <= -p["stop_loss_pct"]:
                    signals.append(
                        ProposedSignal(
                            instrument=instrument,
                            signal_type="exit",
                            action="sell",
                            confidence=0.95,
                            exit_plan=ExitPlan(),
                            reference_price=latest_price,
                            reasoning=f"{instrument}: exit plan hit at {latest_price:.2f}.",
                        )
                    )
                continue

            long_avg = sum(closes[-window:]) / window
            dip_pct = (long_avg - latest_price) / long_avg if long_avg else 0.0
            if dip_pct < p["dip_threshold_pct"]:
                continue

            try:
                fundamentals = self.fundamentals_provider.get_fundamentals(instrument)
            except Exception:  # noqa: BLE001 — a fundamentals lookup failure just skips the candidate
                continue
            if not _passes_quality_gate(fundamentals, p):
                continue

            # Confidence calibration (M2·V5, #36) replaces this placeholder; a deeper price dip
            # against the quality/value gates reads as a stronger setup for now.
            confidence = round(max(0.0, min(1.0, 0.5 + dip_pct)), 4)
            signals.append(
                ProposedSignal(
                    instrument=instrument,
                    signal_type="entry",
                    action="buy",
                    confidence=confidence,
                    exit_plan=ExitPlan(
                        profit_target_pct=p["profit_target_pct"],
                        stop_loss_pct=p["stop_loss_pct"],
                        time_exit_days=p["time_exit_days"],
                    ),
                    reference_price=latest_price,
                    quantity_hint=(account.cash * p["position_cash_fraction"]) / latest_price,
                    strength=dip_pct,
                    reasoning=(
                        f"{instrument}: {dip_pct * 100:.1f}% below its {window}d average, P/E "
                        f"{fundamentals['pe_ratio']:.1f}, dividend yield {fundamentals['dividend_yield'] * 100:.1f}%."
                    ),
                )
            )

        return signals
