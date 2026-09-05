"""The trading pass: one full fetch -> evaluate -> size -> execute pass per environment
(story 11), CLI-triggerable (story 12) via `run_trading_pass(environment, ...)`. Also hosts
`execute_signal`, `approve_signal`, and `reject_signal` — shared by the trading pass (for
auto-approved signals) and the FastAPI approval endpoint (for manually approved ones), so both
paths go through the exact same risk/sizing re-check and kill-switch gate (story 65)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom import calibration, killswitch
from loom.execution.broker import BrokerClient
from loom.market_data.base import MarketDataSource
from loom.models import (
    ApprovalMode,
    Book,
    ConfigVersionStatus,
    Environment,
    Order,
    OrderStatus,
    Signal,
    SignalStatus,
    StrategyConfigVersion,
)
from loom.models import (
    Strategy as StrategyModel,
)
from loom.risk import RiskLimits, size_and_check
from loom.strategy import (
    AccountState,
    ExitPlan,
    MarketData,
    PositionSnapshot,
    ProposedSignal,
    Strategy,
)

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {}


def register_strategy(cls: type[Strategy]) -> type[Strategy]:
    STRATEGY_REGISTRY[cls.key] = cls
    return cls


def get_or_create_book(session: Session, strategy_id: str | None, environment: Environment, name: str) -> Book:
    existing = session.execute(
        select(Book).where(Book.strategy_id == strategy_id, Book.environment == environment)
    ).scalar_one_or_none()
    if existing:
        return existing
    book = Book(strategy_id=strategy_id, environment=environment, name=name)
    session.add(book)
    session.flush()
    return book


def book_positions(session: Session, book_id: str) -> tuple[PositionSnapshot, ...]:
    """Derives current position lots for a book from its filled Orders — Loom's own audit trail
    is the source of truth for book attribution (ADR-0010); the live broker remains the source
    of truth for actual fills/positions overall (ADR-0003)."""
    orders = (
        session.execute(
            select(Order).where(Order.book_id == book_id, Order.status == OrderStatus.filled)
        )
        .scalars()
        .all()
    )
    lots: dict[str, list[float]] = {}  # instrument -> [quantity, avg_price]
    for order in orders:
        signal = session.get(Signal, order.signal_id)
        side = "sell" if signal and signal.action == "sell" else "buy"
        instrument = signal.instrument if signal else None
        if instrument is None:
            continue
        qty, price = lots.get(instrument, [0.0, 0.0])
        if side == "buy":
            new_qty = qty + order.quantity
            price = (price * qty + (order.fill_price or 0.0) * order.quantity) / new_qty if new_qty else 0.0
            qty = new_qty
        else:
            qty = max(0.0, qty - order.quantity)
        lots[instrument] = [qty, price]

    return tuple(
        PositionSnapshot(instrument=i, quantity=q, average_price=p, book_id=book_id)
        for i, (q, p) in lots.items()
        if q > 1e-9
    )


def account_state_for_book(session: Session, book_id: str, broker: BrokerClient) -> AccountState:
    return AccountState(cash=broker.get_cash(), positions=book_positions(session, book_id))


def _decide_approval(
    strategy_row: StrategyModel, confidence: float, manual_override: bool | None
) -> tuple[SignalStatus, bool]:
    if manual_override:
        return SignalStatus.pending_approval, True
    if strategy_row.approval_mode == ApprovalMode.auto:
        return SignalStatus.auto_approved, False
    if strategy_row.approval_mode == ApprovalMode.auto_above_threshold:
        if confidence >= strategy_row.approval_threshold:
            return SignalStatus.auto_approved, False
        return SignalStatus.pending_approval, True
    return SignalStatus.pending_approval, True


DEFAULT_SIGNAL_EXPIRY_HOURS = 24.0


def expire_stale_signals(
    session: Session,
    environment: Environment,
    market_data_source: MarketDataSource,
    max_age_hours: float = DEFAULT_SIGNAL_EXPIRY_HOURS,
    now: datetime | None = None,
) -> list[Signal]:
    """A Signal left un-actioned past `max_age_hours` becomes `expired` (CONTEXT.md "Signal"
    lifecycle) — attaches a counterfactual outcome the same way rejection does (story 66/67),
    since History treats rejected and expired signals identically."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(hours=max_age_hours)
    stale = list(
        session.execute(
            select(Signal).where(
                Signal.environment == environment,
                Signal.status.in_((SignalStatus.pending_approval, SignalStatus.proposed)),
                Signal.created_at < cutoff,
            )
        )
        .scalars()
        .all()
    )

    for signal in stale:
        signal.status = SignalStatus.expired
        signal.decided_at = now
        _attach_counterfactual(signal, market_data_source)
    if stale:
        session.commit()
    return stale


def refresh_counterfactuals(session: Session, environment: Environment, market_data_source: MarketDataSource) -> int:
    """Re-simulates every rejected/expired signal whose shadow position hasn't resolved yet
    ("still-open"). Called at the top of every trading pass, so — in this system's own
    scheduled-single-pass architecture (ADR-0002; there is no long-running daemon to host a
    literal background job) — a shadow position keeps updating on each subsequent pass until it
    resolves or hits its max horizon, exactly as story 67 describes."""
    unresolved = session.execute(
        select(Signal).where(
            Signal.environment == environment,
            Signal.status.in_((SignalStatus.rejected, SignalStatus.expired)),
        )
    ).scalars().all()

    updated = 0
    for signal in unresolved:
        outcome = signal.counterfactual_outcome
        if outcome is None or outcome.get("status") == "still-open":
            _attach_counterfactual(signal, market_data_source)
            updated += 1
    if updated:
        session.commit()
    return updated


def run_trading_pass(
    environment: Environment,
    session: Session,
    broker: BrokerClient,
    market_data_source: MarketDataSource,
    universe: list[str],
    auto_approve_all: bool = False,
    lookback_days: int = 200,
    as_of: str | None = None,
) -> list[Signal]:
    expire_stale_signals(session, environment, market_data_source)
    refresh_counterfactuals(session, environment, market_data_source)

    as_of_date = datetime.utcnow().date() if as_of is None else datetime.fromisoformat(as_of).date()
    start = (as_of_date - timedelta(days=lookback_days)).isoformat()
    end = as_of_date.isoformat()
    market_data = MarketData(
        histories={i: market_data_source.get_history(i, start, end) for i in universe}
    )

    created: list[Signal] = []
    strategy_rows = session.execute(select(StrategyModel)).scalars().all()
    for strategy_row in strategy_rows:
        strategy_cls = STRATEGY_REGISTRY.get(strategy_row.key)
        if strategy_cls is None:
            continue
        if environment == Environment.live and not strategy_row.live_enabled:
            continue

        config_version = session.execute(
            select(StrategyConfigVersion)
            .where(
                StrategyConfigVersion.strategy_id == strategy_row.id,
                StrategyConfigVersion.status == ConfigVersionStatus.promoted,
            )
            .order_by(StrategyConfigVersion.version_number.desc())
        ).scalars().first()
        if config_version is None:
            continue

        book = get_or_create_book(session, strategy_row.id, environment, f"{strategy_row.name} · {environment.value}")
        account = account_state_for_book(session, book.id, broker)
        strategy_impl = strategy_cls.from_config(config_version.params)
        proposed = strategy_impl.generate_signals(market_data, account, account)

        for p in proposed:
            confidence = p.confidence
            if p.signal_type == "entry" and p.strength is not None:
                calibrated = calibration.get_confidence(session, strategy_row.id, config_version.id, p.strength)
                if calibrated is not None:
                    confidence = calibrated

            status, requires_manual = (
                (SignalStatus.auto_approved, False)
                if auto_approve_all
                else _decide_approval(strategy_row, confidence, p.requires_manual_approval_override)
            )
            signal = Signal(
                strategy_id=strategy_row.id,
                config_version_id=config_version.id,
                book_id=book.id,
                environment=environment,
                instrument=p.instrument,
                signal_type=p.signal_type,
                action=p.action,
                confidence=confidence,
                exit_plan=p.exit_plan.as_dict(),
                quantity=p.quantity_hint,
                reference_price=p.reference_price,
                status=status,
                requires_manual_approval=requires_manual,
            )
            session.add(signal)
            session.flush()
            created.append(signal)

            if status == SignalStatus.auto_approved:
                execute_signal(session, signal, broker)

    session.commit()
    return created


def _enum_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _failed_order(signal: Signal, idem_key: str) -> Order:
    return Order(
        signal_id=signal.id,
        book_id=signal.book_id,
        environment=signal.environment,
        idempotency_key=idem_key,
        status=OrderStatus.failed,
        quantity=0,
    )


def execute_signal(session: Session, signal: Signal, broker: BrokerClient, limits: RiskLimits | None = None) -> Order:
    """Re-runs risk/sizing server-side and checks the kill switch immediately before submission —
    used identically whether the signal was auto-approved by the pass or approved via the API
    (story 29, story 65: the fast path never bypasses the safety layer)."""
    limits = limits or RiskLimits()
    idem_key = f"signal-{signal.id}"

    existing = session.execute(select(Order).where(Order.idempotency_key == idem_key)).scalar_one_or_none()
    if existing is not None:
        return existing

    if killswitch.is_engaged(signal.environment):
        order = _failed_order(signal, idem_key)
        session.add(order)
        session.commit()
        return order

    account = account_state_for_book(session, signal.book_id, broker)
    account_value = account.cash + sum(p.quantity * signal.reference_price for p in account.positions)
    proposed = ProposedSignal(
        instrument=signal.instrument,
        signal_type=_enum_value(signal.signal_type),
        action=signal.action,
        confidence=signal.confidence,
        exit_plan=ExitPlan(**signal.exit_plan),
        reference_price=signal.reference_price,
        quantity_hint=signal.quantity,
    )
    decision = size_and_check(proposed, account, account_value, limits)

    if not decision.approved or decision.sized_order is None or decision.sized_order.quantity <= 0:
        order = _failed_order(signal, idem_key)
    else:
        result = broker.submit_order(
            signal.instrument, decision.sized_order.action, decision.sized_order.quantity, idem_key
        )
        order = Order(
            signal_id=signal.id,
            book_id=signal.book_id,
            environment=signal.environment,
            idempotency_key=idem_key,
            broker_order_id=result.broker_order_id,
            status=OrderStatus.filled if result.status == "filled" else OrderStatus.failed,
            quantity=decision.sized_order.quantity,
            fill_price=result.fill_price,
            filled_at=datetime.utcnow() if result.status == "filled" else None,
        )

    session.add(order)
    if order.status == OrderStatus.filled:
        signal.status = SignalStatus.executed
    session.commit()
    return order


def approve_signal(session: Session, signal: Signal, broker: BrokerClient, note: str | None = None) -> Order:
    signal.status = SignalStatus.approved
    signal.note = note
    signal.decided_at = datetime.utcnow()
    session.commit()
    return execute_signal(session, signal, broker)


def reject_signal(
    session: Session, signal: Signal, note: str | None = None, market_data_source: MarketDataSource | None = None
) -> Signal:
    signal.status = SignalStatus.rejected
    signal.note = note
    signal.decided_at = datetime.utcnow()
    if market_data_source is not None:
        _attach_counterfactual(signal, market_data_source)
    session.commit()
    return signal


def _attach_counterfactual(signal: Signal, market_data_source: MarketDataSource) -> None:
    """Simulates the rejected signal forward as a shadow position (story 67) using the
    backtest engine's own fill logic, reused single-signal via loom.backtest.counterfactual."""
    from loom.backtest.counterfactual import simulate_counterfactual

    signal.counterfactual_outcome = simulate_counterfactual(
        instrument=signal.instrument,
        entry_date=signal.created_at.date().isoformat(),
        entry_price=signal.reference_price,
        exit_plan=ExitPlan(**signal.exit_plan),
        source=market_data_source,
    )
