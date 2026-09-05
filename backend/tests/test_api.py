"""Approval pipeline exercised through real HTTP requests via the FastAPI app (Testing
Decisions, issue #1: the approval -> execution path is tested through real routing/serialization,
not by calling internals, since it's user-facing and money-moving)."""

import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/api_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_strategies_seeded_on_startup(client):
    resp = client.get("/strategies")
    assert resp.status_code == 200
    keys = [s["key"] for s in resp.json()]
    assert "low_vol_compounder" in keys


def test_approval_pipeline_end_to_end(client):
    strategy_id = client.get("/strategies").json()[0]["id"]
    client.patch(f"/strategies/{strategy_id}", json={"approval_mode": "manual"})
    client.post("/trading-pass/run", params={"environment": "demo"})

    signals = client.get("/signals", params={"environment": "demo", "status": "pending_approval"}).json()
    assert signals, "expected at least one pending signal from the fixture universe"
    signal = signals[0]
    assert signal["status"] == "pending_approval"

    insight = client.post(f"/signals/{signal['id']}/screen").json()
    assert insight["tier"] == "screening"
    assert signal["instrument"] in insight["content"]

    approved = client.post(f"/signals/{signal['id']}/approve", json={"note": "looks good"}).json()
    assert approved["status"] == "executed"
    assert approved["note"] == "looks good"

    overview = client.get("/overview", params={"environment": "demo"}).json()
    assert any(p["instrument"] == signal["instrument"] for p in overview["positions"])

    history = client.get("/history", params={"environment": "demo"}).json()
    assert any(h["id"] == signal["id"] for h in history)


def test_reject_records_decision(client):
    client.post("/trading-pass/run", params={"environment": "demo"})
    signals = client.get("/signals", params={"environment": "demo", "status": "pending_approval"}).json()
    signal = signals[0]

    rejected = client.post(f"/signals/{signal['id']}/reject", json={"note": "pass"}).json()

    assert rejected["status"] == "rejected"
    assert rejected["note"] == "pass"


def test_kill_switch_engage_blocks_approval(client):
    client.post("/trading-pass/run", params={"environment": "demo"})
    client.post("/settings/kill-switch/engage", params={"environment": "demo"})
    assert client.get("/settings/kill-switch", params={"environment": "demo"}).json()["engaged"] is True

    signals = client.get("/signals", params={"environment": "demo", "status": "pending_approval"}).json()
    signal = signals[0]

    approved = client.post(f"/signals/{signal['id']}/approve", json={}).json()

    assert approved["status"] == "approved"  # decision recorded...
    orders_status = client.get(f"/signals/{signal['id']}").json()
    assert orders_status["status"] == "approved"  # ...but never reaches "executed"

    client.post("/settings/kill-switch/resume", params={"environment": "demo"})
    assert client.get("/settings/kill-switch", params={"environment": "demo"}).json()["engaged"] is False


def test_draft_backtest_and_promote(client):
    strategy_id = client.get("/strategies").json()[0]["id"]

    draft_resp = client.post(
        f"/strategies/{strategy_id}/draft-backtest",
        json={
            "strategy_id": strategy_id,
            "draft_params": {"volatility_threshold": 0.03},
            "universe": ["VUSA.L"],
            "start": "2023-01-02",
            "end": "2023-04-30",
            "starting_capital": 10_000,
        },
    ).json()
    assert "backtest" in draft_resp
    assert "volatility_threshold" in draft_resp["param_diff"]

    created = client.post(
        f"/strategies/{strategy_id}/config-versions",
        json={"params": {"volatility_threshold": 0.03}, "note": "loosen the vol filter"},
    ).json()
    assert created["status"] == "draft"

    promoted = client.post(f"/strategies/{strategy_id}/config-versions/{created['id']}/promote").json()
    assert promoted["status"] == "promoted"
    assert promoted["version_number"] == 2
