"""API authentication (ADR-0017): the shared-secret header, its two exemptions, and the
fail-closed behavior when no key is configured.

The endpoints asserted on here are deliberately the money-moving and safety-control ones — the
chain an anonymous caller could previously walk to enable live trading, clear the kill switch and
run a live pass.
"""

import pytest
from fastapi.testclient import TestClient

from loom import db
from tests.conftest import TEST_API_KEY


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/auth_test.db")
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


NO_KEY = {"X-Loom-Api-Key": ""}

SAFETY_CONTROL_ENDPOINTS = [
    ("post", "/settings/live-trading-gate/enable"),
    ("post", "/settings/auto-trading-gate/enable"),
    ("post", "/settings/kill-switch/resume"),
    ("post", "/trading-pass/run"),
    ("get", "/overview"),
    ("get", "/strategies"),
]


@pytest.mark.parametrize(("method", "path"), SAFETY_CONTROL_ENDPOINTS)
def test_rejects_requests_with_no_api_key(client, method, path):
    resp = getattr(client, method)(path, headers=NO_KEY)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid or missing API key"


@pytest.mark.parametrize(("method", "path"), SAFETY_CONTROL_ENDPOINTS)
def test_rejects_requests_with_a_wrong_api_key(client, method, path):
    resp = getattr(client, method)(path, headers={"X-Loom-Api-Key": TEST_API_KEY + "-wrong"})
    assert resp.status_code == 401


def test_accepts_requests_with_the_configured_api_key(client):
    assert client.get("/strategies").status_code == 200


def test_a_rejected_request_never_reaches_the_handler(client):
    """The strategy list is seeded at startup, so a 401 that still returned data would be a
    middleware that runs *after* routing rather than in front of it."""
    resp = client.patch("/strategies/any-id", json={"live_enabled": True}, headers=NO_KEY)
    assert resp.status_code == 401
    assert "live_enabled" not in resp.text


def test_health_is_exempt_so_cloud_run_probes_still_pass(client):
    assert client.get("/health", headers=NO_KEY).json() == {"status": "ok"}


def test_action_links_are_exempt_and_carry_their_own_signed_token(client):
    """Emailed one-tap approve/reject (story 64) is opened from a mail client with no API key.
    It is reachable, but an invalid token is still refused by the link's own verification."""
    resp = client.get("/action-links/not-a-real-token", headers=NO_KEY)
    assert resp.status_code == 200  # renders an HTML failure page, not an auth error
    assert "unknown action link" in resp.text


def test_fails_closed_when_no_key_is_configured(client, monkeypatch):
    """An unset LOOM_API_KEY must refuse every protected request rather than serve them
    unauthenticated — the misconfiguration this module exists to prevent."""
    monkeypatch.setenv("LOOM_API_KEY", "")
    resp = client.post("/settings/live-trading-gate/enable", headers={"X-Loom-Api-Key": TEST_API_KEY})
    assert resp.status_code == 503
    assert "LOOM_API_KEY is not configured" in resp.json()["detail"]
