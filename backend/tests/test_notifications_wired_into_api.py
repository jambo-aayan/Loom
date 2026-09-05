"""Confirms the API endpoints actually call the notification dispatch layer (not just that the
dispatch layer works in isolation, already covered by test_notification_dispatch.py)."""

import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/wired_test.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def test_kill_switch_engage_sends_an_email(client):
    from loom.api.deps import get_email_sender

    sender = get_email_sender()
    before = len(sender.sent)

    client.post("/settings/kill-switch/engage", params={"environment": "demo"})

    assert len(sender.sent) == before + 1
    assert "kill switch" in sender.sent[-1][1].lower()


def test_kill_switch_resume_sends_an_email(client):
    from loom.api.deps import get_email_sender

    client.post("/settings/kill-switch/engage", params={"environment": "demo"})
    sender = get_email_sender()
    before = len(sender.sent)

    client.post("/settings/kill-switch/resume", params={"environment": "demo"})

    assert len(sender.sent) == before + 1


def test_trading_pass_run_emails_every_pending_signal(client):
    from loom.api.deps import get_email_sender

    sender = get_email_sender()
    before = len(sender.sent)

    signals = client.post("/trading-pass/run", params={"environment": "demo"}).json()
    pending = [s for s in signals if s["status"] == "pending_approval"]

    assert len(sender.sent) == before + len(pending)
