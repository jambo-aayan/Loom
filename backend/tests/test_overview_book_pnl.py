import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/overview_pnl_test.db")
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


def test_overview_reports_per_book_pnl_for_a_strategy_book(client):
    strategy_id = client.get("/strategies").json()[0]["id"]
    client.patch(f"/strategies/{strategy_id}", json={"approval_mode": "auto"})
    client.post("/trading-pass/run", params={"environment": "demo"})

    overview = client.get("/overview", params={"environment": "demo"}).json()

    assert overview["book_pnl"], "expected at least one Book with a computed P&L"
    entry = overview["book_pnl"][0]
    assert entry["market_value"] > 0
    assert entry["cost_basis"] > 0
    assert "unrealized_pnl" in entry
    assert "unrealized_pnl_pct" in entry


def test_overview_reports_manual_book_pnl(client):
    from loom.api.deps import get_broker
    from loom.execution.broker import BrokerPosition
    from loom.models import Environment

    get_broker(Environment.demo).positions["AAPL"] = BrokerPosition(instrument="AAPL", quantity=10, average_price=150.0)

    overview = client.get("/overview", params={"environment": "demo"}).json()

    manual_pnl = next(b for b in overview["book_pnl"] if b["book_name"] == "Manual")
    assert manual_pnl["strategy_key"] is None
    assert manual_pnl["cost_basis"] == 1500.0


def test_overview_book_pnl_is_empty_when_no_positions(client):
    overview = client.get("/overview", params={"environment": "demo"}).json()

    assert overview["book_pnl"] == []
