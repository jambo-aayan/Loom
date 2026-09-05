from datetime import date

from loom.backtest.counterfactual import simulate_counterfactual
from loom.market_data.base import MarketDataSource
from loom.strategy import Bar, ExitPlan, InstrumentHistory


class ScriptedSource(MarketDataSource):
    def __init__(self, closes: dict[str, float]):
        self.closes = closes

    def get_history(self, instrument, start, end):
        bars = tuple(Bar(date=d, open=c, high=c, low=c, close=c) for d, c in self.closes.items())
        return InstrumentHistory(instrument, bars)


def test_counterfactual_hits_profit_target():
    source = ScriptedSource({"2024-01-01": 100.0, "2024-01-02": 101.0, "2024-01-03": 105.0})
    outcome = simulate_counterfactual(
        instrument="X",
        entry_date="2024-01-01",
        entry_price=100.0,
        exit_plan=ExitPlan(profit_target_pct=0.04, stop_loss_pct=0.02),
        source=source,
    )
    assert outcome["status"] == "hit-target"
    assert outcome["exit_date"] == "2024-01-03"
    assert outcome["return_pct"] == 0.05


def test_counterfactual_hits_stop_loss():
    source = ScriptedSource({"2024-01-01": 100.0, "2024-01-02": 97.0})
    outcome = simulate_counterfactual(
        instrument="X",
        entry_date="2024-01-01",
        entry_price=100.0,
        exit_plan=ExitPlan(profit_target_pct=0.04, stop_loss_pct=0.02),
        source=source,
    )
    assert outcome["status"] == "hit-stop"


def test_counterfactual_still_open_when_neither_hit():
    source = ScriptedSource({"2024-01-01": 100.0, "2024-01-02": 100.5})
    outcome = simulate_counterfactual(
        instrument="X",
        entry_date="2024-01-01",
        entry_price=100.0,
        exit_plan=ExitPlan(profit_target_pct=0.04, stop_loss_pct=0.02),
        source=source,
        max_horizon_days=1,
        as_of=date(2024, 1, 2),
    )
    assert outcome["status"] == "still-open"
