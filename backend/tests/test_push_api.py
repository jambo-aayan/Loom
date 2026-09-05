import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/push_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_vapid_public_key_empty_by_default(client):
    resp = client.get("/push/vapid-public-key")
    assert resp.status_code == 200
    assert resp.json()["public_key"] is None


def test_subscribe_then_unsubscribe(client):
    body = {"endpoint": "https://push.example/device-1", "p256dh": "key", "auth": "secret", "environment": "demo"}

    resp = client.post("/push/subscribe", json=body)
    assert resp.status_code == 200
    assert resp.json()["status"] == "subscribed"

    again = client.post("/push/subscribe", json=body)
    assert again.json()["status"] == "already subscribed"

    unsub = client.post("/push/unsubscribe", params={"endpoint": body["endpoint"]})
    assert unsub.json()["status"] == "unsubscribed"
