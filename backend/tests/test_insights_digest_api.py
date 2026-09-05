import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/insights_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_digest_rejects_unknown_period(client):
    resp = client.get("/insights/digest", params={"environment": "demo", "period": "monthly"})
    assert resp.status_code == 400


def test_digest_empty_when_no_insights_yet(client):
    resp = client.get("/insights/digest", params={"environment": "demo", "period": "daily"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["fired"] == []
    assert body["still_watching"] == []


def test_digest_splits_pending_from_decided(client):
    client.post("/trading-pass/run", params={"environment": "demo"})
    signals = client.get("/signals", params={"environment": "demo"}).json()
    assert signals
    client.post("/signals/screen-pending", params={"environment": "demo"})

    resp = client.get("/insights/digest", params={"environment": "demo", "period": "daily"})
    body = resp.json()
    total = len(body["fired"]) + len(body["still_watching"])
    assert total == len(signals)
    for entry in body["still_watching"]:
        assert entry["status"] == "pending_approval"


def test_signal_chart_returns_bars_and_trigger_point(client):
    client.post("/trading-pass/run", params={"environment": "demo"})
    signals = client.get("/signals", params={"environment": "demo"}).json()
    assert signals
    signal = signals[0]

    resp = client.get(f"/insights/signals/{signal['id']}/chart", params={"window_days": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert body["instrument"] == signal["instrument"]
    assert body["trigger"]["price"] == signal["reference_price"]
    assert len(body["bars"]) > 0


def test_signal_chart_404_for_unknown_signal(client):
    resp = client.get("/insights/signals/does-not-exist/chart")
    assert resp.status_code == 404
