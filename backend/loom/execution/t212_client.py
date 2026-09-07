"""Custom Trading 212 API client (ADR-0006). Paces itself off the `x-ratelimit-*` response
headers rather than fixed sleeps (story 9), logs every request/response (story 10), and is
built against FakeBrokerClient's contract in tests — this class itself is exercised separately
against recorded HTTP fixtures (Testing Decisions, issue #1), not by the main test suite, since
it needs a real Demo API key and network access this sandbox doesn't have.

Auth is HTTP Basic: the API key as username, the API secret as password (per T212's own API
docs) — not the raw key alone as earlier code assumed.

Order idempotency: T212's own order endpoints are documented as not idempotent, and don't accept
or honor any client-supplied order identifier — there is no `clientOrderId` field, so a
pre-submission "does this already exist" check can't actually prevent a duplicate. Loom instead
relies entirely on the DB-level `Order.idempotency_key` unique constraint, generated before this
client is ever called (ADR-0014); this client submits every call it's given.
"""

from __future__ import annotations

import logging
import time

import httpx

from loom.execution.broker import BrokerClient, BrokerPosition, OrderResult

logger = logging.getLogger("loom.t212")


class Trading212ResponseError(RuntimeError):
    """A T212 response didn't match the shape this client expects — raised rather than silently
    defaulting to a placeholder value (e.g. treating an account with an unrecognized cash shape
    as having £0 available), since a wrong number here is a real-money mistake waiting to happen."""


class Trading212Client(BrokerClient):
    def __init__(self, base_url: str, api_key: str, api_secret: str, client: httpx.Client | None = None):
        self.base_url = base_url
        self._client = client or httpx.Client(
            base_url=base_url, auth=httpx.BasicAuth(api_key, api_secret), timeout=15.0
        )

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        logger.info("t212 request %s %s params=%s json=%s", method, path, kwargs.get("params"), kwargs.get("json"))
        response = self._client.request(method, path, **kwargs)
        logger.info("t212 response %s %s -> %s %s", method, path, response.status_code, response.text[:500])
        self._pace_from_headers(response.headers)
        return response

    @staticmethod
    def _pace_from_headers(headers: httpx.Headers) -> None:
        remaining = headers.get("x-ratelimit-remaining")
        reset_seconds = headers.get("x-ratelimit-reset")
        if remaining is not None and reset_seconds is not None:
            try:
                if int(remaining) <= 0:
                    time.sleep(max(0.0, float(reset_seconds)))
            except ValueError:
                pass

    def submit_order(self, instrument: str, side: str, quantity: float, idempotency_key: str) -> OrderResult:
        response = self._request(
            "POST",
            "/equity/orders/market",
            json={
                "ticker": instrument,
                "quantity": quantity if side in ("buy", "add") else -quantity,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return OrderResult(
            broker_order_id=str(payload.get("id")),
            status=payload.get("status", "submitted"),
            fill_price=payload.get("fillPrice"),
        )

    def get_positions(self) -> list[BrokerPosition]:
        response = self._request("GET", "/equity/positions")
        response.raise_for_status()
        return [
            BrokerPosition(
                instrument=row["ticker"], quantity=row["quantity"], average_price=row["averagePrice"]
            )
            for row in response.json()
        ]

    def get_cash(self) -> float:
        """Reads `GET /equity/account/summary`'s nested `cash.availableToTrade` (the current
        T212 API shape) — fails loudly on anything else rather than defaulting to 0.0, since a
        silent wrong answer here would misprice every subsequent sizing decision."""
        response = self._request("GET", "/equity/account/summary")
        response.raise_for_status()
        payload = response.json()
        cash = payload.get("cash")
        if not isinstance(cash, dict) or "availableToTrade" not in cash:
            raise Trading212ResponseError(
                f"unexpected /equity/account/summary shape, expected cash.availableToTrade: {payload!r}"
            )
        return float(cash["availableToTrade"])
