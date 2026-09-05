"""Ticket #32's explicit acceptance criterion: the add-on-weakness action is always
pending-approval regardless of confidence or the strategy's configured Approval mode — verified
end-to-end through run_trading_pass with an `auto`-mode Harvester."""

from loom import strategies  # noqa: F401
from loom.execution.broker import FakeBrokerClient
from loom.models import (
    ApprovalMode,
    ConfigVersionStatus,
    Environment,
    SignalStatus,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import Strategy as StrategyModel
from loom.strategies.volatility_harvester import DEFAULT_PARAMS
from loom.strategy import Bar, InstrumentHistory
from loom.trading_pass import book_positions, get_or_create_book, run_trading_pass


class _ScriptedSource:
    """A deterministic source built so the Harvester reads a deep-but-inside-stop-loss pullback
    on a held position — the scenario that should trigger add-on-weakness (see
    tests/test_volatility_harvester.py for the same construction, explained there)."""

    def __init__(self):
        bars = [Bar(date=f"2024-01-{i + 1:02d}", open=100, high=100.1, low=99.9, close=100) for i in range(29)]
        bars.append(Bar(date="2024-01-30", open=100, high=100, low=97, close=97))
        self._history = InstrumentHistory("TSLA", tuple(bars))

    def get_history(self, instrument, start, end):
        return self._history

    def universe(self):
        return ["TSLA"]


def test_add_on_action_stays_pending_even_in_auto_approval_mode(session):
    strategy = StrategyModel(
        key="volatility_harvester",
        name="Volatility Harvester",
        style=StrategyStyle.trading,
        approval_mode=ApprovalMode.auto,  # the strategy itself would auto-approve everything else
    )
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params=dict(DEFAULT_PARAMS)
    )
    session.add(config)
    session.flush()

    # Seed an existing losing position bought near the top of the flat band (see
    # test_volatility_harvester.py for why 101 keeps the loss inside the stop-loss percentage).
    book = get_or_create_book(session, strategy.id, Environment.demo, "Harvester · demo")
    from loom.models import Order, OrderStatus, Signal, SignalType

    seed_signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument="TSLA",
        signal_type=SignalType.entry,
        action="buy",
        confidence=0.8,
        exit_plan={"profit_target_pct": None, "stop_loss_pct": None, "time_exit_days": None},
        quantity=10,
        reference_price=101.0,
        status=SignalStatus.executed,
    )
    session.add(seed_signal)
    session.flush()
    session.add(
        Order(
            signal_id=seed_signal.id,
            book_id=book.id,
            environment=Environment.demo,
            idempotency_key="seed-order",
            status=OrderStatus.filled,
            quantity=10,
            fill_price=101.0,
        )
    )
    session.commit()
    assert book_positions(session, book.id), "seed position must actually be held before the pass"

    source = _ScriptedSource()
    signals = run_trading_pass(Environment.demo, session, FakeBrokerClient(), source, universe=source.universe())

    add_ons = [s for s in signals if s.action == "add"]
    assert add_ons, "expected an add-on-weakness signal for this deep-but-inside-stop pullback"
    assert add_ons[0].status == SignalStatus.pending_approval
    assert add_ons[0].requires_manual_approval is True
