"""Reviewing dry-run exit decisions (#56).

The dry run exists to be read — as a correctness check, and more importantly as a parameter
audit, since no exit parameter in the roster has ever been tested against reality (D0).
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from loom import db
from loom.exit_pass import run_exit_pass
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import Environment


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/obs.db")
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def _seed_observations(session, entry_date, price):
    from tests.test_exit_pass import _PricedBroker, _held

    _held(session, entry=100.0, plan={"profit_target_pct": 0.5, "stop_loss_pct": 0.05, "time_exit_days": None})
    run_exit_pass(
        Environment.demo, session, _PricedBroker({"TSLA": price}), FixtureMarketDataSource(),
        as_of=entry_date, now=datetime.fromisoformat(f"{entry_date}T12:00:00"),
    )


def test_returns_nothing_before_any_pass_has_run(client):
    body = client.get("/exit-observations?environment=demo").json()
    assert body["total"] == 0
    assert body["by_strategy"] == []


def test_decisions_are_grouped_by_strategy_with_the_audit_fields(session):
    _seed_observations(session, "2024-03-06", price=90.0)

    from loom.api.routers.exit_observations import list_exit_observations

    body = list_exit_observations(environment="demo", session=session)
    assert body["total"] == 1
    group = body["by_strategy"][0]
    assert group["strategy"] == "Volatility Harvester"
    decision = group["decisions"][0]
    assert decision["instrument"] == "TSLA"
    assert decision["exit_reason"] == "stop loss"
    assert decision["decision_price"] == 90.0
    assert decision["entry_date"] == "2024-01-02"
    assert decision["hold_days"] == 64
    assert decision["exit_plan"]["stop_loss_pct"] == 0.05


def test_a_stop_firing_long_after_entry_is_not_flagged_as_a_fast_stop(session):
    _seed_observations(session, "2024-03-06", price=90.0)  # 64 days held

    from loom.api.routers.exit_observations import list_exit_observations

    group = list_exit_observations(environment="demo", session=session)["by_strategy"][0]
    assert group["fast_stops"] == 0
    assert group["decisions"][0]["fast_stop"] is False


def test_a_stop_firing_days_after_entry_is_flagged(session):
    """The single most useful reading in this data: a stop that fires within days of entry is
    usually measuring noise rather than risk."""
    _seed_observations(session, "2024-01-04", price=90.0)  # 2 days held

    from loom.api.routers.exit_observations import list_exit_observations

    group = list_exit_observations(environment="demo", session=session)["by_strategy"][0]
    assert group["fast_stops"] == 1
    assert group["decisions"][0]["fast_stop"] is True


def test_observations_are_scoped_per_environment(session):
    _seed_observations(session, "2024-03-06", price=90.0)

    from loom.api.routers.exit_observations import list_exit_observations

    assert list_exit_observations(environment="demo", session=session)["total"] == 1
    assert list_exit_observations(environment="live", session=session)["total"] == 0


def test_dry_run_decisions_never_reach_approvals(client, session):
    """The whole reason these live in their own table."""
    _seed_observations(session, "2024-03-06", price=90.0)
    assert client.get("/signals?environment=demo&status=pending_approval").json() == []
