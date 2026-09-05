import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/position_insight_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    monkeypatch.setattr("loom.api.deps._fake_brokers", {})
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_position_commentary_for_a_manual_holding(client):
    from loom.api.deps import get_broker
    from loom.execution.broker import BrokerPosition
    from loom.models import Environment

    get_broker(Environment.demo).positions["AAPL"] = BrokerPosition(instrument="AAPL", quantity=10, average_price=150.0)

    overview = client.get("/overview", params={"environment": "demo"}).json()
    manual_position = next(p for p in overview["positions"] if p["instrument"] == "AAPL")
    assert manual_position["book_name"] == "Manual"

    resp = client.post(f"/insights/positions/{manual_position['book_id']}/AAPL")

    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "position"
    assert body["signal_id"] is None
    assert body["book_id"] == manual_position["book_id"]
    assert "AAPL" in body["content"]


def test_position_commentary_for_a_strategy_owned_position(client):
    strategy_id = client.get("/strategies").json()[0]["id"]
    client.patch(f"/strategies/{strategy_id}", json={"approval_mode": "auto"})

    signals = client.post("/trading-pass/run", params={"environment": "demo"}).json()
    executed = [s for s in signals if s["status"] == "executed"]
    assert executed, "expected the auto-approved strategy to execute at least one order"
    signal = executed[0]

    resp = client.post(f"/insights/positions/{signal['book_id']}/{signal['instrument']}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "position"
    assert body["signal_id"] is None
    assert body["book_id"] == signal["book_id"]


def test_position_commentary_404s_for_unknown_book(client):
    resp = client.post("/insights/positions/does-not-exist/AAPL")
    assert resp.status_code == 404


def test_position_commentary_404s_when_no_open_position(client):
    from loom.api.deps import get_broker
    from loom.execution.broker import BrokerPosition
    from loom.models import Environment

    get_broker(Environment.demo).positions["AAPL"] = BrokerPosition(instrument="AAPL", quantity=10, average_price=150.0)
    overview = client.get("/overview", params={"environment": "demo"}).json()
    manual_position = next(p for p in overview["positions"] if p["instrument"] == "AAPL")

    resp = client.post(f"/insights/positions/{manual_position['book_id']}/TSLA")

    assert resp.status_code == 404
