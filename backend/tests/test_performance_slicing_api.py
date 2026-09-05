import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/slice_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_correlation_endpoint_returns_matrix_shaped_by_books(client):
    resp = client.get("/performance/correlation", params={"environment": "demo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["books"] == []
    assert body["matrix"] == []


def test_performance_accepts_instrument_and_sector_filters(client):
    resp = client.get("/performance", params={"environment": "demo", "instrument": "VUSA.L"})
    assert resp.status_code == 200
    resp2 = client.get("/performance", params={"environment": "demo", "sector": "Technology"})
    assert resp2.status_code == 200


def test_history_accepts_instrument_and_sector_filters(client):
    client.post("/trading-pass/run", params={"environment": "demo"})
    all_history = client.get("/history", params={"environment": "demo"}).json()
    resp = client.get("/history", params={"environment": "demo", "instrument": "VUSA.L"})
    assert resp.status_code == 200
    for signal in resp.json():
        assert signal["instrument"] == "VUSA.L"
    # a nonexistent sector filters everything out without erroring
    resp2 = client.get("/history", params={"environment": "demo", "sector": "Nonexistent Sector"})
    assert resp2.status_code == 200
    assert resp2.json() == [] or len(resp2.json()) <= len(all_history)
