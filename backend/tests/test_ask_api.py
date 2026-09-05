import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ask_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_ask_returns_an_answer(client):
    resp = client.post("/insights/ask", json={"question": "What's driving oil prices this week?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["question"] == "What's driving oil prices this week?"
    assert body["instrument"] is None
    assert "oil prices" in body["answer"]


def test_ask_can_be_scoped_to_an_instrument(client):
    resp = client.post("/insights/ask", json={"question": "Any recent earnings news?", "instrument": "AAPL"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["instrument"] == "AAPL"
    assert "AAPL" in body["answer"]


def test_ask_rejects_a_blank_question(client):
    resp = client.post("/insights/ask", json={"question": "   "})
    assert resp.status_code == 400


def test_ask_produces_no_signal_order_or_approval_side_effects(client):
    signals_before = client.get("/signals", params={"environment": "demo"}).json()

    client.post("/insights/ask", json={"question": "Should I buy TSLA?"})

    signals_after = client.get("/signals", params={"environment": "demo"}).json()
    assert signals_after == signals_before
