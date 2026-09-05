import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/action_links_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_approve_action_link_executes_the_signal(client):
    client.post("/trading-pass/run", params={"environment": "demo"})
    signals = client.get("/signals", params={"environment": "demo", "status": "pending_approval"}).json()
    assert signals
    signal_id = signals[0]["id"]

    from loom import db as db_module
    from loom.notifications.email import generate_action_link

    session = next(db_module.get_session())
    url = generate_action_link(session, signal_id, "approve")
    token = url.rsplit("/", 1)[-1]

    resp = client.get(f"/action-links/{token}")
    assert resp.status_code == 200
    assert "Approved" in resp.text

    updated = client.get(f"/signals/{signal_id}").json()
    assert updated["status"] == "executed"


def test_action_link_is_single_use(client):
    client.post("/trading-pass/run", params={"environment": "demo"})
    signals = client.get("/signals", params={"environment": "demo", "status": "pending_approval"}).json()
    signal_id = signals[0]["id"]

    from loom import db as db_module
    from loom.notifications.email import generate_action_link

    session = next(db_module.get_session())
    url = generate_action_link(session, signal_id, "reject")
    token = url.rsplit("/", 1)[-1]

    first = client.get(f"/action-links/{token}")
    assert "Rejected" in first.text

    second = client.get(f"/action-links/{token}")
    assert "already been used" in second.text


def test_unknown_action_link_token(client):
    resp = client.get("/action-links/does-not-exist")
    assert resp.status_code == 200
    assert "unknown action link" in resp.text
