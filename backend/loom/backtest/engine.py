"""Backtest engine: reuses the live Strategy interface; a simulated portfolio/fill engine applies
historical prices to a simulated cash/position ledger; a stepping fake clock only exposes data up
to the simulated "now", preventing lookahead (Testing Decisions, issue #1). Auto-approves every
signal (no human available on historical data) while still enforcing real risk/sizing (story 45).

The single-instrument fill/exit logic (`_advance_trade`) is reused forward-in-time and
single-signal by loom.backtest.counterfactual for shadow-position simulation (story 67).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from loom.market_data.base import MarketDataSource
from loom.risk import RiskLimits, size_and_check
from loom.strategy import (
    AccountState,
    Bar,
    ExitPlan,
    InstrumentHistory,
    MarketData,
    PositionSnapshot,
    Strategy,
)


@dataclass
class TradeRecord:
    instrument: str
    entry_date: str
    entry_price: float
    quantity: float
    exit_plan: ExitPlan
    exit_date: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    entry_strength: float | None = None  # the ProposedSignal.strength that opened this trade —
    # confidence calibration (loom.calibration) buckets historical trades by this.

    @property
    def is_open(self) -> bool:
        return self.exit_date is None

    @property
    def return_pct(self) -> float | None:
        return None if self.exit_price is None else (self.exit_price - self.entry_price) / self.entry_price

    @property
    def pnl(self) -> float | None:
        return None if self.exit_price is None else (self.exit_price - self.entry_price) * self.quantity

    @property
    def hold_days(self) -> int | None:
        if self.exit_date is None:
            return None
        return (date.fromisoformat(self.exit_date) - date.fromisoformat(self.entry_date)).days


@dataclass
class EquityPoint:
    date: str
    equity: float
    benchmark_equity: float


@dataclass
class BacktestResult:
    trades: list[TradeRecord]
    equity_curve: list[EquityPoint]
    stats: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "trades": [
                {
                    "instrument": t.instrument,
                    "entry_date": t.entry_date,
                    "entry_price": t.entry_price,
                    "entry_strength": t.entry_strength,
                    "quantity": t.quantity,
                    "exit_date": t.exit_date,
                    "exit_price": t.exit_price,
                    "exit_reason": t.exit_reason,
                    "return_pct": t.return_pct,
                    "pnl": t.pnl,
                    "hold_days": t.hold_days,
                    "is_open": t.is_open,
                }
                for t in self.trades
            ],
            "equity_curve": [
                {"date": e.date, "equity": e.equity, "benchmark_equity": e.benchmark_equity}
                for e in self.equity_curve
            ],
            "stats": self.stats,
        }


def _business_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _bar_on(history: InstrumentHistory, d: date) -> Bar | None:
    iso = d.isoformat()
    for bar in history.bars:
        if bar.date == iso:
            return bar
    return None


def check_exit(trade: TradeRecord, current_price: float, current_date: date) -> tuple[bool, str | None]:
    """Shared exit-check logic: profit target, stop loss, or time-based exit. Reused by the
    portfolio-wide backtest loop and by single-signal counterfactual simulation."""
    change_pct = (current_price - trade.entry_price) / trade.entry_price
    plan = trade.exit_plan
    if plan.profit_target_pct is not None and change_pct >= plan.profit_target_pct:
        return True, "profit target"
    if plan.stop_loss_pct is not None and change_pct <= -plan.stop_loss_pct:
        return True, "stop loss"
    if plan.time_exit_days is not None:
        held = (current_date - date.fromisoformat(trade.entry_date)).days
        if held >= plan.time_exit_days:
            return True, "time exit"
    return False, None


def run_backtest(
    strategy: Strategy,
    source: MarketDataSource,
    universe: list[str],
    start: str,
    end: str,
    starting_capital: float,
    limits: RiskLimits | None = None,
) -> BacktestResult:
    limits = limits or RiskLimits()
    start_d, end_d = date.fromisoformat(start), date.fromisoformat(end)
    full_histories = {i: source.get_history(i, start, end) for i in universe}

    cash = starting_capital
    open_trades: dict[str, TradeRecord] = {}
    closed_trades: list[TradeRecord] = []
    equity_curve: list[EquityPoint] = []

    bench_units = {
        i: (starting_capital / len(universe)) / full_histories[i].bars[0].close
        for i in universe
        if full_histories[i].bars
    }

    for d in _business_days(start_d, end_d):
        iso = d.isoformat()
        truncated = {
            i: InstrumentHistory(i, tuple(b for b in h.bars if b.date <= iso))
            for i, h in full_histories.items()
        }
        market_data = MarketData(histories=truncated)

        position_snapshots = tuple(
            PositionSnapshot(t.instrument, t.quantity, t.entry_price, book_id="backtest")
            for t in open_trades.values()
        )
        equity_now = cash + sum(
            t.quantity * (_bar_on(full_histories[t.instrument], d) or Bar(iso, 0, 0, 0, t.entry_price)).close
            for t in open_trades.values()
        )
        account = AccountState(cash=cash, positions=position_snapshots)

        # 1. Check exits (explicit exit-plan hits) before evaluating new entries.
        for instrument in list(open_trades.keys()):
            bar = _bar_on(full_histories[instrument], d)
            if bar is None:
                continue
            trade = open_trades[instrument]
            should_exit, reason = check_exit(trade, bar.close, d)
            if should_exit:
                cash += trade.quantity * bar.close
                trade.exit_date, trade.exit_price, trade.exit_reason = iso, bar.close, reason
                closed_trades.append(trade)
                del open_trades[instrument]

        # 2. Ask the strategy for signals given data truncated to `d` — no lookahead.
        signals = strategy.generate_signals(market_data, account, account)
        for signal in signals:
            bar = _bar_on(full_histories.get(signal.instrument, InstrumentHistory(signal.instrument, ())), d)
            if bar is None:
                continue
            if signal.action == "sell" and signal.instrument in open_trades:
                trade = open_trades.pop(signal.instrument)
                cash += trade.quantity * bar.close
                trade.exit_date, trade.exit_price = iso, bar.close
                trade.exit_reason = signal.reasoning or "strategy exit signal"
                closed_trades.append(trade)
                continue
            if signal.action in ("buy", "add") and signal.instrument not in open_trades:
                decision = size_and_check(signal, account, equity_now, limits)
                if not decision.approved or decision.sized_order is None:
                    continue
                order = decision.sized_order
                if order.quantity <= 0:
                    continue
                cash -= order.quantity * bar.close
                open_trades[signal.instrument] = TradeRecord(
                    instrument=signal.instrument,
                    entry_date=iso,
                    entry_price=bar.close,
                    quantity=order.quantity,
                    exit_plan=signal.exit_plan,
                    entry_strength=signal.strength,
                )

        equity_now = cash + sum(
            t.quantity * (_bar_on(full_histories[t.instrument], d) or Bar(iso, 0, 0, 0, t.entry_price)).close
            for t in open_trades.values()
        )
        bench_equity = sum(
            units * (_bar_on(full_histories[i], d) or Bar(iso, 0, 0, 0, 0)).close
            for i, units in bench_units.items()
        )
        equity_curve.append(EquityPoint(date=iso, equity=equity_now, benchmark_equity=bench_equity))

    all_trades = closed_trades + list(open_trades.values())
    stats = _compute_stats(starting_capital, equity_curve, closed_trades)
    return BacktestResult(trades=all_trades, equity_curve=equity_curve, stats=stats)


def _compute_stats(starting_capital: float, equity_curve: list[EquityPoint], closed_trades: list[TradeRecord]) -> dict:
    if not equity_curve:
        return {}
    final_equity = equity_curve[-1].equity
    final_bench = equity_curve[-1].benchmark_equity
    peak = starting_capital
    max_drawdown = 0.0
    for point in equity_curve:
        peak = max(peak, point.equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - point.equity) / peak)

    wins = [t for t in closed_trades if (t.pnl or 0) > 0]
    return {
        "total_return_pct": (final_equity - starting_capital) / starting_capital,
        "benchmark_return_pct": (final_bench - starting_capital) / starting_capital
        if starting_capital
        else 0.0,
        "num_trades": len(closed_trades),
        "win_rate": (len(wins) / len(closed_trades)) if closed_trades else 0.0,
        "max_drawdown_pct": max_drawdown,
        "final_equity": final_equity,
    }
