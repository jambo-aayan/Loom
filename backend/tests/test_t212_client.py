"""Unit tests against a mocked httpx transport (no real network/credentials needed) — verifies
request construction and response parsing. The module docstring's "exercised separately against
recorded HTTP fixtures" refers to end-to-end verification against T212's real API, which this
sandbox can't reach; that's a separate, additional check, not a replacement for these."""

import base64

import httpx
import pytest

from loom.execution.t212_client import Trading212Client, Trading212ResponseError


def _client(handler) -> Trading212Client:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://demo.trading212.com/api/v0",
        auth=httpx.BasicAuth("test-key", "test-secret"),
        transport=transport,
    )
    return Trading212Client(
        base_url="https://demo.trading212.com/api/v0",
        api_key="test-key",
        api_secret="test-secret",
        client=http_client,
    )


def test_requests_use_http_basic_auth_with_key_and_secret():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        return httpx.Response(200, json={})

    client = _client(handler)
    client._request("GET", "/equity/positions")

    expected = "Basic " + base64.b64encode(b"test-key:test-secret").decode()
    assert seen["authorization"] == expected


def test_submit_order_sends_no_client_order_id_and_never_pre_checks(monkeypatch):
    """ADR-0014: no fabricated clientOrderId, and no pre-submission duplicate-check call —
    every submit_order call results in exactly one HTTP request."""
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json={"id": 42, "status": "submitted"})

    client = _client(handler)
    client.submit_order("VUSA.L", "buy", 5, idempotency_key="signal-abc")

    assert len(requests_seen) == 1
    body = requests_seen[0].content
    assert b"clientOrderId" not in body


def test_submit_order_negates_quantity_for_a_sell():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 1, "status": "submitted"})

    client = _client(handler)
    client.submit_order("VUSA.L", "sell", 5, idempotency_key="signal-abc")

    assert captured["body"]["quantity"] == -5


def test_get_positions_hits_equity_positions():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v0/equity/positions"
        return httpx.Response(200, json=[{"ticker": "VUSA.L", "quantity": 10, "averagePrice": 100.0}])

    client = _client(handler)
    positions = client.get_positions()

    assert positions[0].instrument == "VUSA.L"
    assert positions[0].quantity == 10


def test_get_cash_parses_nested_account_summary_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v0/equity/account/summary"
        return httpx.Response(200, json={"cash": {"availableToTrade": 1234.56}})

    client = _client(handler)

    assert client.get_cash() == 1234.56


def test_get_cash_fails_loudly_on_an_unrecognized_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"free": 1234.56})  # the old, wrong shape

    client = _client(handler)

    with pytest.raises(Trading212ResponseError):
        client.get_cash()
