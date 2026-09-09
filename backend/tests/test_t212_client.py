"""Unit tests against a mocked httpx transport (no real network/credentials needed) — verifies
request construction and response parsing. The module docstring's "exercised separately against
recorded HTTP fixtures" refers to end-to-end verification against T212's real API, which this
sandbox can't reach; that's a separate, additional check, not a replacement for these."""

import base64

import httpx
import pytest

from loom.execution.t212_client import Trading212Client, Trading212ResponseError
from loom.execution.t212_tickers import UnmappedInstrumentError


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
    every submit_order call results in exactly one HTTP request (a terminal status straight
    away means no polling follow-up either)."""
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json={"id": 42, "status": "FILLED", "filledQuantity": 5, "filledValue": 500.0})

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
        return httpx.Response(200, json={"id": 1, "status": "FILLED", "filledQuantity": 5, "filledValue": 500.0})

    client = _client(handler)
    client.submit_order("VUSA.L", "sell", 5, idempotency_key="signal-abc")

    assert captured["body"]["quantity"] == -5


def test_submit_order_rounds_quantity_down_to_four_decimal_places():
    """T212 rejects a market order with more than 4 decimal places of quantity precision
    (confirmed live: "invalid quantity precision 4") — our own sizing math produces full float
    precision. Rounds down, not to nearest, so it never requests more than risk/sizing approved."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 1, "status": "FILLED", "filledQuantity": 3.5824, "filledValue": 358.24})

    client = _client(handler)
    client.submit_order("VUSA.L", "buy", 3.582431566679713, idempotency_key="signal-abc")

    assert captured["body"]["quantity"] == 3.5824


def test_submit_order_polls_when_the_synchronous_response_is_not_yet_filled(monkeypatch):
    """Confirmed live: a real market order's synchronous POST response can come back "NEW"
    (filledQuantity=0), then actually fill moments later. submit_order must poll
    GET /equity/orders/{id} rather than recording a live fill as a failure."""
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        if request.method == "POST":
            return httpx.Response(200, json={"id": 99, "status": "NEW", "filledQuantity": 0})
        assert str(request.url).endswith("/equity/orders/99")
        if len(calls) < 3:
            return httpx.Response(200, json={"id": 99, "status": "NEW", "filledQuantity": 0})
        return httpx.Response(200, json={"id": 99, "status": "FILLED", "filledQuantity": 5, "filledValue": 500.0})

    client = _client(handler)
    result = client.submit_order("VUSA.L", "buy", 5, idempotency_key="signal-abc")

    assert result.status == "filled"
    assert result.fill_price == 100.0
    assert len(calls) == 3  # 1 POST + 2 polls before reaching FILLED


def test_submit_order_stops_polling_after_a_max_number_of_attempts(monkeypatch):
    """An order stuck non-terminal (never resolves within the poll budget) must not hang the
    request forever — give up and record it as failed rather than loop indefinitely."""
    monkeypatch.setattr("time.sleep", lambda _: None)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json={"id": 1, "status": "NEW", "filledQuantity": 0})

    client = _client(handler)
    result = client.submit_order("VUSA.L", "buy", 5, idempotency_key="signal-abc")

    assert result.status == "failed"
    assert len(calls) == 9  # 1 POST + 8 polls, then give up


def test_submit_order_normalizes_t212s_uppercase_filled_status():
    """T212's real status values are uppercase lifecycle states (FILLED, NEW, REJECTED, ...),
    not the lowercase "filled"/"failed" OrderResult.status contract (broker.py)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": 1, "status": "FILLED", "filledQuantity": 5, "filledValue": 500.0})

    client = _client(handler)
    result = client.submit_order("VUSA.L", "buy", 5, idempotency_key="signal-abc")

    assert result.status == "filled"
    assert result.fill_price == 100.0


def test_submit_order_fails_locally_without_a_network_call_when_quantity_rounds_to_zero():
    """A high-priced instrument sized to a tiny fraction of cash can round down to zero at the
    4-decimal-place cap — that should be a clean local failure, not a wasted network call and a
    confusing 400 from T212."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should never reach the network when quantity rounds to zero")

    client = _client(handler)
    result = client.submit_order("VUSA.L", "buy", 0.00004, idempotency_key="signal-abc")

    assert result.status == "failed"


def test_submit_order_treats_anything_short_of_filled_as_failed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": 1, "status": "REJECTED"})

    client = _client(handler)
    result = client.submit_order("VUSA.L", "buy", 5, idempotency_key="signal-abc")

    assert result.status == "failed"
    assert result.fill_price is None


def test_submit_order_translates_to_t212s_own_ticker():
    """T212 uses its own internal ticker codes, not the market-data-style ones the rest of Loom
    uses — confirmed live: submitting "TSLA" as-is 404s, T212 only recognizes "TSLA_US_EQ"."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 1, "status": "FILLED", "filledQuantity": 5, "filledValue": 500.0})

    client = _client(handler)
    client.submit_order("TSLA", "buy", 5, idempotency_key="signal-abc")

    assert captured["body"]["ticker"] == "TSLA_US_EQ"


def test_submit_order_fails_loudly_for_an_unmapped_instrument():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should never reach the network for an unmapped instrument")

    client = _client(handler)
    with pytest.raises(UnmappedInstrumentError):
        client.submit_order("UNKNOWN.X", "buy", 5, idempotency_key="signal-abc")


def test_get_positions_hits_equity_positions():
    """Real shape confirmed live against a non-empty position (never exercised before — every
    earlier check happened to see an empty account): ticker is nested under "instrument", and
    the price field is "averagePricePaid", not the flat "ticker"/"averagePrice" once assumed."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v0/equity/positions"
        return httpx.Response(
            200,
            json=[
                {
                    "instrument": {"ticker": "VUSAl_EQ", "name": "Vanguard S&P 500 (Dist)"},
                    "quantity": 10,
                    "averagePricePaid": 100.0,
                }
            ],
        )

    client = _client(handler)
    positions = client.get_positions()

    assert positions[0].instrument == "VUSA.L"  # translated back to Loom's own naming
    assert positions[0].quantity == 10
    assert positions[0].average_price == 100.0


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
