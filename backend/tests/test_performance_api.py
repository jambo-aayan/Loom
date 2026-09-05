import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/perf_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_performance_aggregate_with_no_trades_yet(client):
    resp = client.get("/performance", params={"environment": "demo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["aggregate_metrics"]["num_trades"] == 0
    assert body["aggregate_curve"] == []
    assert body["per_book"] == []


def test_performance_reflects_a_real_executed_trade(client):
    client.post("/trading-pass/run", params={"environment": "demo"})
    signals = client.get("/signals", params={"environment": "demo", "status": "pending_approval"}).json()
    assert signals
    client.post(f"/signals/{signals[0]['id']}/approve", json={})

    books = client.get("/books", params={"environment": "demo"}).json()
    assert books

    resp = client.get("/performance", params={"environment": "demo"})
    body = resp.json()
    assert body["per_book"]
    # a single open (not yet closed) position produces zero *closed* trades — that's expected
    assert body["aggregate_metrics"]["num_trades"] == 0


def test_book_performance_404_for_unknown_book(client):
    resp = client.get("/performance/books/does-not-exist")
    assert resp.status_code == 404
