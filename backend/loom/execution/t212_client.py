"""Custom Trading 212 API client (ADR-0006). Paces itself off the `x-ratelimit-*` response
headers rather than fixed sleeps (story 9), logs every request/response (story 10), and is
built against FakeBrokerClient's contract in tests — this class itself is exercised separately
against recorded HTTP fixtures (Testing Decisions, issue #1), not by the main test suite, since
it needs a real Demo API key and network access this sandbox doesn't have.
"""

from __future__ import annotations

import logging
import time

import httpx

from loom.execution.broker import BrokerClient, BrokerPosition, OrderResult

logger = logging.getLogger("loom.t212")


class Trading212Client(BrokerClient):
    def __init__(self, base_url: str, api_key: str, client: httpx.Client | None = None):
        self.base_url = base_url
        self.api_key = api_key
        self._client = client or httpx.Client(
            base_url=base_url, headers={"Authorization": api_key}, timeout=15.0
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

    def find_pending_order(self, idempotency_key: str) -> dict | None:
        """Checked before resubmission so a retried/timed-out request never double-submits a
        real trade (story 8) — Trading 212's own order endpoints aren't idempotent."""
        response = self._request("GET", "/equity/orders")
        response.raise_for_status()
        for order in response.json():
            if order.get("clientOrderId") == idempotency_key:
                return order
        return None

    def submit_order(self, instrument: str, side: str, quantity: float, idempotency_key: str) -> OrderResult:
        existing = self.find_pending_order(idempotency_key)
        if existing is not None:
            return OrderResult(
                broker_order_id=str(existing.get("id")),
                status=existing.get("status", "submitted"),
                fill_price=existing.get("fillPrice"),
            )

        response = self._request(
            "POST",
            "/equity/orders/market",
            json={
                "ticker": instrument,
                "quantity": quantity if side in ("buy", "add") else -quantity,
                "clientOrderId": idempotency_key,
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
        response = self._request("GET", "/equity/portfolio")
        response.raise_for_status()
        return [
            BrokerPosition(
                instrument=row["ticker"], quantity=row["quantity"], average_price=row["averagePrice"]
            )
            for row in response.json()
        ]

    def get_cash(self) -> float:
        response = self._request("GET", "/equity/account/cash")
        response.raise_for_status()
        return float(response.json().get("free", 0.0))
