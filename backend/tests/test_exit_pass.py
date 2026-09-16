"""Exit enforcement layer, dry run (#53, ADR-0018).

Driven through the entrypoint with the existing faked broker, fixture market data, a real
database and an injected clock — no new external boundary.
"""

from datetime import datetime

import pytest

from loom import killswitch
from loom.execution.broker import BrokerPosition, FakeBrokerClient
from loom.exit_pass import is_within_exit_window, run_exit_pass
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import Environment, ExitObservation, Order, Signal, SignalStatus
from loom.trading_pass import book_positions
from tests.test_book_positions_add_count import _fill, _seed_book

NOON_WEEKDAY = datetime(2024, 3, 6, 12, 0)


class _PricedBroker(FakeBrokerClient):
    """A broker that reports a live price, the way Trading 212 does for a held instrument."""

    def __init__(self, prices: dict[str, float]):
        super().__init__(starting_cash=10_000, fill_price=100.0)
        self._prices = prices

    def get_positions(self):
        return [BrokerPosition(i, 10.0, 100.0, current_price=p) for i, p in self._prices.items()]


def _held(session, *, entry=100.0, plan=None):
    strategy, config, book = _seed_book(session)
    _fill(session, strategy, config, book, "buy", entry, 10, datetime(2024, 1, 2))
    if plan is not None:
        signal = session.execute(select_signal(book.id)).scalars().first()
        signal.exit_plan = plan
        session.commit()
    return strategy, config, book


def select_signal(book_id):
    from sqlalchemy import select

    return select(Signal).where(Signal.book_id == book_id)


# --- market window -------------------------------------------------------------------

@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (datetime(2024, 3, 6, 12, 0), True),   # midweek, both sessions live
        (datetime(2024, 3, 6, 8, 0), True),    # LSE open
        (datetime(2024, 3, 6, 20, 59), True),  # US still open
        (datetime(2024, 3, 6, 7, 59), False),  # before the LSE
        (datetime(2024, 3, 6, 21, 0), False),  # after the US close
        (datetime(2024, 3, 9, 12, 0), False),  # Saturday
        (datetime(2024, 3, 10, 12, 0), False),  # Sunday
    ],
)
def test_exit_window(moment, expected):
    assert is_within_exit_window(moment) is expected


def test_pass_is_a_no_op_outside_the_window(session):
    _held(session, plan={"profit_target_pct": 0.01, "stop_loss_pct": 0.01, "time_exit_days": 1})
    decisions = run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 200.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=datetime(2024, 3, 6, 22, 0),
    )
    assert decisions == []
    assert session.query(ExitObservation).count() == 0


# --- decisions -----------------------------------------------------------------------

def test_a_position_past_its_profit_target_is_decided_for_exit(session):
    _held(session, entry=100.0, plan={"profit_target_pct": 0.05, "stop_loss_pct": 0.5, "time_exit_days": None})
    decisions = run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 110.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON_WEEKDAY,
    )
    assert [(d.instrument, d.exit_reason) for d in decisions] == [("TSLA", "profit target")]


def test_a_position_past_its_stop_is_decided_for_exit(session):
    _held(session, entry=100.0, plan={"profit_target_pct": 0.5, "stop_loss_pct": 0.05, "time_exit_days": None})
    decisions = run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 90.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON_WEEKDAY,
    )
    assert [d.exit_reason for d in decisions] == ["stop loss"]


def test_a_position_within_its_plan_is_left_alone(session):
    _held(session, entry=100.0, plan={"profit_target_pct": 0.5, "stop_loss_pct": 0.5, "time_exit_days": None})
    assert run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 101.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON_WEEKDAY,
    ) == []


def test_a_position_with_no_plan_is_never_touched(session):
    """Reconciled holdings in the Manual book carry no plan and must be left entirely alone."""
    _held(session, plan={"profit_target_pct": None, "stop_loss_pct": None, "time_exit_days": None})
    assert run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 500.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON_WEEKDAY,
    ) == []


def test_a_decision_records_hold_duration_and_the_plan_it_evaluated(session):
    """These rows are a parameter audit as much as a correctness check (gap analysis D0)."""
    _held(session, entry=100.0, plan={"profit_target_pct": 0.05, "stop_loss_pct": 0.5, "time_exit_days": None})
    run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 110.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON_WEEKDAY,
    )
    observation = session.query(ExitObservation).one()
    assert observation.entry_date == "2024-01-02"
    assert observation.hold_days == 64
    assert observation.exit_plan["profit_target_pct"] == 0.05
    assert observation.decision_price == 110.0
    assert observation.quantity == 10.0


# --- inertness -----------------------------------------------------------------------

def test_a_dry_run_changes_nothing(session):
    """Asserted as a property of the run, not by example: no Order, no Signal, nothing pending."""
    _held(session, entry=100.0, plan={"profit_target_pct": 0.05, "stop_loss_pct": 0.5, "time_exit_days": None})
    orders_before = session.query(Order).count()
    signals_before = session.query(Signal).count()

    decisions = run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 110.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON_WEEKDAY,
    )

    assert decisions, "nothing was decided, so inertness proves nothing"
    assert session.query(Order).count() == orders_before
    assert session.query(Signal).count() == signals_before
    assert session.query(Signal).filter(Signal.status == SignalStatus.pending_approval).count() == 0
    assert book_positions(session, decisions[0].book_id)[0].quantity == 10.0


# --- kill switch ---------------------------------------------------------------------

def test_nothing_is_proposed_while_the_kill_switch_is_engaged(session):
    _held(session, entry=100.0, plan={"profit_target_pct": 0.05, "stop_loss_pct": 0.5, "time_exit_days": None})
    killswitch.engage(session, Environment.demo, actor="test")

    decisions = run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": 110.0}), FixtureMarketDataSource(),
        as_of="2024-03-06", now=NOON_WEEKDAY,
    )

    assert decisions == []
    # Not even an observation: a frequent job that proposed and was blocked would manufacture a
    # failed Order every run (ADR-0018).
    assert session.query(ExitObservation).count() == 0
