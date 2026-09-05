import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/reconciliation_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_overview_surfaces_an_untracked_broker_position_as_manual(client, monkeypatch):
    monkeypatch.setattr("loom.api.deps._fake_brokers", {})

    from loom.api.deps import get_broker
    from loom.execution.broker import BrokerPosition
    from loom.models import Environment

    broker = get_broker(Environment.demo)
    broker.positions["AAPL"] = BrokerPosition(instrument="AAPL", quantity=4, average_price=175.0)

    overview = client.get("/overview", params={"environment": "demo"}).json()

    manual_entries = [p for p in overview["positions"] if p["instrument"] == "AAPL"]
    assert len(manual_entries) == 1
    assert manual_entries[0]["book_name"] == "Manual"
    assert manual_entries[0]["strategy_key"] is None
    assert manual_entries[0]["quantity"] == 4
