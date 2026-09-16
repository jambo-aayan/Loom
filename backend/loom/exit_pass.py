"""The exit enforcement layer (ADR-0018, #53).

One place decides whether a held `Position` should close, sharing its logic with the backtest
engine via `check_exit` so live and backtest agree by construction rather than by convention. It
runs on its own schedule, far more often than the daily entry pass: entries are patient by design
(ADR-0002), exits are not, and a stop checked once a day is not a stop.

This module only *decides*. Whether a decision is acted on is #58's concern; until then every run
is a dry run that records what it would have done and sells nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom import exit_enforcement, killswitch
from loom.backtest.engine import check_exit
from loom.execution.broker import BrokerClient
from loom.market_data.base import MarketDataSource
from loom.models import Book, Environment, ExitObservation, Signal, SignalStatus, SignalType
from loom.strategy import ExitPlan, PositionSnapshot
from loom.trading_pass import book_positions, execute_signal, open_lot_opening_signal

logger = logging.getLogger("loom.exit_pass")

# One window spanning both sessions Loom trades: the LSE runs roughly 08:00-16:30 UTC and the US
# 14:30-21:00. A per-exchange window is the better answer but needs instrument metadata that does
# not exist yet, and outside an instrument's own hours the broker price simply does not move — so
# a check then is a no-op rather than a wrong answer (ADR-0018).
EXIT_WINDOW_OPEN_HOUR_UTC = 8
EXIT_WINDOW_CLOSE_HOUR_UTC = 21


def is_within_exit_window(now: datetime) -> bool:
    """Weekday, and inside the combined LSE/US session. A pure function of the clock so the job
    is a cheap no-op out of hours and this is directly testable."""
    if now.weekday() >= 5:
        return False
    return EXIT_WINDOW_OPEN_HOUR_UTC <= now.hour < EXIT_WINDOW_CLOSE_HOUR_UTC


# An exit realising a pre-calculated level is arithmetic, not a forecast (ADR-0009) — there is
# nothing for a human to judge, so it reads as high-confidence by construction, the same value the
# strategies already use for their own plan-based exits.
PLAN_EXIT_CONFIDENCE = 0.95


@dataclass(frozen=True)
class ExitDecision:
    """One position the layer decided should close. Returned from the pass and, in dry run,
    persisted as an `ExitObservation`."""

    book_id: str
    strategy_id: str | None
    instrument: str
    exit_reason: str
    decision_price: float
    quantity: float
    entry_date: str | None
    hold_days: int | None
    exit_plan: ExitPlan
    opening_signal_id: str | None = None


def _price_for(
    instrument: str,
    broker_prices: dict[str, float],
    market_data_source: MarketDataSource,
    as_of: date,
) -> float | None:
    """The broker's own live price for a held instrument, falling back to market data.

    Preferring the broker matters for coherence as much as freshness: Loom already displays P&L
    from this number, and an exit firing off a different price than the one on screen would be
    indefensible to the person watching it happen.
    """
    live = broker_prices.get(instrument)
    if live is not None:
        return live
    history = market_data_source.get_history(instrument, as_of.isoformat(), as_of.isoformat())
    if history.bars:
        return history.bars[-1].close
    logger.warning("no price available for %s — skipping its exit evaluation this run", instrument)
    return None


def _peak_since_entry(
    instrument: str, entry_date: str | None, as_of: date, market_data_source: MarketDataSource
) -> float | None:
    """The highest price reached since the position opened, derived on each evaluation rather
    than stored (#57).

    Deriving beats a stored watermark on two counts: there is no mutable state to keep in sync,
    and a missed job run or a restart cannot corrupt a live stop — the answer is recomputed from
    the bars every time. Uses the bar high, not the close, because a trailing stop that ignores
    intraday highs is not measuring the peak.
    """
    if entry_date is None:
        return None
    history = market_data_source.get_history(instrument, entry_date, as_of.isoformat())
    return max((bar.high for bar in history.bars), default=None)


def _decide(
    position: PositionSnapshot,
    exit_plan: ExitPlan,
    price: float,
    as_of: date,
    strategy_id: str | None,
    peak_price: float | None = None,
    opening_signal_id: str | None = None,
) -> ExitDecision | None:
    should_exit, reason = check_exit(
        entry_price=position.average_price,
        entry_date=position.entry_date or as_of.isoformat(),
        exit_plan=exit_plan,
        current_price=price,
        current_date=as_of,
        peak_price=peak_price,
    )
    if not should_exit or reason is None:
        return None
    held = (as_of - date.fromisoformat(position.entry_date)).days if position.entry_date else None
    return ExitDecision(
        book_id=position.book_id,
        strategy_id=strategy_id,
        instrument=position.instrument,
        exit_reason=reason,
        decision_price=price,
        quantity=position.quantity,
        entry_date=position.entry_date,
        hold_days=held,
        exit_plan=exit_plan,
        opening_signal_id=opening_signal_id,
    )


def run_exit_pass(
    environment: Environment,
    session: Session,
    broker: BrokerClient,
    market_data_source: MarketDataSource,
    as_of: str | None = None,
    now: datetime | None = None,
) -> list[ExitDecision]:
    """Evaluate every open `Position` carrying an `Exit plan`, in any `Book`.

    Records what it would have done and sells nothing — acting on a decision is #58.
    """
    now = now or datetime.utcnow()
    as_of_date = datetime.fromisoformat(as_of).date() if as_of else now.date()

    if killswitch.is_engaged(session, environment):
        # Propose nothing at all, rather than proposing and having execution block it. A frequent
        # job doing the latter manufactures a failed Order every run (ADR-0018).
        logger.info("kill switch engaged for %s — exit pass proposing nothing", environment.value)
        return []

    if not is_within_exit_window(now):
        return []

    broker_prices = {p.instrument: p.current_price for p in broker.get_positions() if p.current_price is not None}

    decisions: list[ExitDecision] = []
    books = session.execute(select(Book).where(Book.environment == environment)).scalars().all()
    for book in books:
        for position in book_positions(session, book.id):
            opening = open_lot_opening_signal(session, book.id, position.instrument)
            if opening is None or not opening.exit_plan:
                # No plan, nothing to enforce. Reconciled holdings in the Manual book are the
                # common case and must be left alone.
                continue
            plan = ExitPlan(**opening.exit_plan)
            if not any(
                (plan.profit_target_pct, plan.stop_loss_pct, plan.time_exit_days, plan.trailing_stop_pct)
            ):
                continue
            price = _price_for(position.instrument, broker_prices, market_data_source, as_of_date)
            if price is None:
                continue
            # Only fetched when a trailing stop is actually configured — no plan in the current
            # roster sets one, so this costs nothing until one does.
            peak = (
                _peak_since_entry(position.instrument, position.entry_date, as_of_date, market_data_source)
                if plan.trailing_stop_pct is not None
                else None
            )
            decision = _decide(
                position,
                plan,
                price,
                as_of_date,
                book.strategy_id,
                peak_price=peak,
                opening_signal_id=opening.id,
            )
            if decision is not None:
                decisions.append(decision)

    if exit_enforcement.is_enforcing(session, environment):
        _execute(session, environment, broker, decisions)
        return decisions

    for decision in decisions:
        session.add(
            ExitObservation(
                environment=environment,
                book_id=decision.book_id,
                strategy_id=decision.strategy_id,
                instrument=decision.instrument,
                exit_reason=decision.exit_reason,
                decision_price=decision.decision_price,
                quantity=decision.quantity,
                entry_date=decision.entry_date,
                hold_days=decision.hold_days,
                exit_plan=decision.exit_plan.as_dict(),
                observed_at=now,
            )
        )
    if decisions:
        session.commit()

    logger.info(
        "exit pass (%s, dry run): %d position(s) would have exited", environment.value, len(decisions)
    )
    return decisions


def _execute(
    session: Session, environment: Environment, broker: BrokerClient, decisions: list[ExitDecision]
) -> None:
    """Turn each decision into a `Signal` and submit it.

    Auto-approved rather than queued: an exit realising a level calculated at entry is arithmetic
    (ADR-0009), so there is nothing for a human to judge, and a stop that waits for a click is not
    a stop. The `Auto-trading gate` is deliberately not consulted — it governs entries and
    discretionary exits, because a circuit breaker that stopped you closing a losing position
    would be the wrong shape. The `Kill switch` still outranks everything and was already checked
    before any of this ran.

    Attribution is inherited from the `Signal` that opened the position: that signal's `Strategy`
    owns the `Book`, and its plan is the one being realised, so the exit genuinely belongs to it.
    Inheriting also means no schema change — a nullable strategy link on `Order` would break
    booked-trade attribution, History and per-Book P&L, which all traverse order to signal.
    """
    for decision in decisions:
        opening = session.get(Signal, decision.opening_signal_id) if decision.opening_signal_id else None
        if opening is None:
            logger.warning(
                "no opening signal for %s in book %s — cannot attribute an exit, skipping",
                decision.instrument,
                decision.book_id,
            )
            continue

        signal = Signal(
            strategy_id=opening.strategy_id,
            config_version_id=opening.config_version_id,
            book_id=decision.book_id,
            environment=environment,
            instrument=decision.instrument,
            signal_type=SignalType.exit,
            action="sell",
            confidence=PLAN_EXIT_CONFIDENCE,
            exit_plan={},  # an exit closes a position; it does not open one needing a plan
            quantity=decision.quantity,
            reference_price=decision.decision_price,
            status=SignalStatus.auto_approved,
            requires_manual_approval=False,
        )
        session.add(signal)
        session.flush()
        # Through the same chokepoint as every other order: kill switch, live gate, and the full
        # risk/sizing re-check. The speed of an automatic exit never bypasses the safety layer.
        execute_signal(session, signal, broker)

    session.commit()
    logger.info("exit pass (%s, enforcing): executed %d exit(s)", environment.value, len(decisions))
