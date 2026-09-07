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
            {"t212_demo_api_key": "", "t212_demo_api_secret": "", "t212_demo_base_url": "https://demo.trading212.com/api/v0"},
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
            {"t212_demo_api_key": "some-key", "t212_demo_api_secret": "", "t212_demo_base_url": "https://demo.trading212.com/api/v0"},
        )(),
    )

    assert isinstance(get_broker(Environment.demo), FakeBrokerClient)


def test_uses_real_client_when_both_key_and_secret_are_set(monkeypatch):
    monkeypatch.setattr(
        "loom.api.deps.get_settings",
        lambda: type(
            "S",
            (),
            {"t212_demo_api_key": "some-key", "t212_demo_api_secret": "some-secret", "t212_demo_base_url": "https://demo.trading212.com/api/v0"},
        )(),
    )

    assert isinstance(get_broker(Environment.demo), Trading212Client)
