from loom.api.deps import get_broker
from loom.execution.broker import FakeBrokerClient
from loom.execution.t212_client import Trading212Client
from loom.models import Environment


def test_falls_back_to_fake_broker_with_no_credentials(monkeypatch):
    monkeypatch.setattr(
        "loom.api.deps.get_settings",
        lambda: type(
            "S",
            (),
            {"t212_api_key": "", "t212_api_secret": "", "t212_demo_base_url": "https://demo.trading212.com/api/v0"},
        )(),
    )

    assert isinstance(get_broker(Environment.demo), FakeBrokerClient)


def test_falls_back_to_fake_broker_with_only_a_key_and_no_secret(monkeypatch):
    """A partially-configured environment (key set, secret missing) must not silently construct
    a real client that would just 401 — fall back to the fake broker instead."""
    monkeypatch.setattr(
        "loom.api.deps.get_settings",
        lambda: type(
            "S",
            (),
            {"t212_api_key": "some-key", "t212_api_secret": "", "t212_demo_base_url": "https://demo.trading212.com/api/v0"},
        )(),
    )

    assert isinstance(get_broker(Environment.demo), FakeBrokerClient)


def test_uses_real_client_when_both_key_and_secret_are_set(monkeypatch):
    monkeypatch.setattr(
        "loom.api.deps.get_settings",
        lambda: type(
            "S",
            (),
            {"t212_api_key": "some-key", "t212_api_secret": "some-secret", "t212_demo_base_url": "https://demo.trading212.com/api/v0"},
        )(),
    )

    assert isinstance(get_broker(Environment.demo), Trading212Client)


def test_the_same_credential_is_used_for_both_environments(monkeypatch):
    """A T212 account issues one key+secret pair total — not one per demo/live — so both
    environments must resolve to a real client off the exact same t212_api_key/secret, differing
    only in base_url."""
    monkeypatch.setattr(
        "loom.api.deps.get_settings",
        lambda: type(
            "S",
            (),
            {
                "t212_api_key": "some-key",
                "t212_api_secret": "some-secret",
                "t212_demo_base_url": "https://demo.trading212.com/api/v0",
                "t212_live_base_url": "https://live.trading212.com/api/v0",
            },
        )(),
    )

    demo_broker = get_broker(Environment.demo)
    live_broker = get_broker(Environment.live)

    assert isinstance(demo_broker, Trading212Client) and isinstance(live_broker, Trading212Client)
    assert demo_broker.base_url == "https://demo.trading212.com/api/v0"
    assert live_broker.base_url == "https://live.trading212.com/api/v0"
