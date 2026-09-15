import pytest

from loom import auto_trading_gate, db, live_trading_gate


@pytest.fixture()
def session():
    db.init_db("sqlite:///:memory:")
    gen = db.get_session()
    s = next(gen)
    yield s
    try:
        next(gen)
    except StopIteration:
        pass


@pytest.fixture(autouse=True)
def _gates_open_by_default(session):
    """The global auto-trading/live-trading gates (CONTEXT.md) default OFF in production, but
    most of this suite predates them and assumes auto-approval and live-environment order
    submission just work. Enabled here via the same session every session-based test already
    uses, so those tests don't need updating one-by-one. A test that specifically exercises
    gate-off behavior calls auto_trading_gate.disable(session)/live_trading_gate.disable(session)
    itself partway through, which simply adds a later, overriding event row.

    Tests reached through a `client` fixture (a separate TestClient-backed app/DB, not this
    `session`) are NOT covered by this fixture — those enable the gate explicitly via the API
    when a specific test needs it (e.g. `client.post("/settings/auto-trading-gate/enable")`),
    since most client-based tests use `approval_mode: manual` and never need it at all."""
    auto_trading_gate.enable(session, actor="test-default")
    live_trading_gate.enable(session, actor="test-default")


TEST_API_KEY = "test-loom-api-key"


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    """Every API test builds its own `TestClient` locally (14 files do), so rather than editing
    each one to pass the ADR-0017 auth header, set the key in the environment and give TestClient
    a default header. A test that specifically exercises *missing* or *wrong* credentials
    overrides the header on the individual request, which takes precedence over this default.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("LOOM_API_KEY", TEST_API_KEY)

    original_init = TestClient.__init__

    def _with_api_key(self, *args, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("X-Loom-Api-Key", TEST_API_KEY)
        original_init(self, *args, headers=headers, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", _with_api_key)
