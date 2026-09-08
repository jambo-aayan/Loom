from loom.api.deps import get_broker
from loom.execution.broker import FakeBrokerClient
from loom.execution.t212_client import Trading212Client
from loom.models import Environment


def _settings(**overrides):
    base = {
        "t212_demo_api_key": "",
        "t212_demo_api_secret": "",
        "t212_live_api_key": "",
        "t212_live_api_secret": "",
        "t212_demo_base_url": "https://demo.trading212.com/api/v0",
        "t212_live_base_url": "https://live.trading212.com/api/v0",
    }
    base.update(overrides)
    return type("S", (), base)()


def test_falls_back_to_fake_broker_with_no_credentials(monkeypatch):
    monkeypatch.setattr("loom.api.deps.get_settings", lambda: _settings())

    assert isinstance(get_broker(Environment.demo), FakeBrokerClient)


def test_falls_back_to_fake_broker_with_only_a_key_and_no_secret(monkeypatch):
    """A partially-configured environment (key set, secret missing) must not silently construct
    a real client that would just 401 — fall back to the fake broker instead."""
    monkeypatch.setattr(
        "loom.api.deps.get_settings", lambda: _settings(t212_demo_api_key="some-key")
    )

    assert isinstance(get_broker(Environment.demo), FakeBrokerClient)


def test_uses_real_client_when_both_key_and_secret_are_set(monkeypatch):
    monkeypatch.setattr(
        "loom.api.deps.get_settings",
        lambda: _settings(t212_demo_api_key="some-key", t212_demo_api_secret="some-secret"),
    )

    assert isinstance(get_broker(Environment.demo), Trading212Client)


def test_demo_and_live_use_separate_credentials(monkeypatch):
    """T212's Practice (demo) mode and live mode are separate API systems with separate
    credentials — a key generated in one mode does not authenticate against the other's base
    URL, so each environment must resolve to its own key+secret, not a shared one."""
    monkeypatch.setattr(
        "loom.api.deps.get_settings",
        lambda: _settings(
            t212_demo_api_key="demo-key",
            t212_demo_api_secret="demo-secret",
            t212_live_api_key="live-key",
            t212_live_api_secret="live-secret",
        ),
    )

    demo_broker = get_broker(Environment.demo)
    live_broker = get_broker(Environment.live)

    assert isinstance(demo_broker, Trading212Client) and isinstance(live_broker, Trading212Client)
    assert demo_broker.base_url == "https://demo.trading212.com/api/v0"
    assert live_broker.base_url == "https://live.trading212.com/api/v0"
    assert demo_broker._client.auth is not live_broker._client.auth


def test_demo_stays_on_fake_broker_when_only_live_credentials_are_set(monkeypatch):
    """A live-mode key must never get used against the demo base URL, or vice versa — if only
    live credentials are configured, demo must still fall back to the fake broker rather than
    reusing the live credential."""
    monkeypatch.setattr(
        "loom.api.deps.get_settings",
        lambda: _settings(t212_live_api_key="live-key", t212_live_api_secret="live-secret"),
    )

    assert isinstance(get_broker(Environment.demo), FakeBrokerClient)
    assert isinstance(get_broker(Environment.live), Trading212Client)
