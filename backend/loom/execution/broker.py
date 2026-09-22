"""Broker interface: the seam faked in tests (Testing Decisions, issue #1) and implemented for
real by Trading212Client (execution/t212_client.py)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OrderResult:
    broker_order_id: str
    status: str  # "filled" | "failed" | "submitted"
    fill_price: float | None = None


@dataclass
class BrokerPosition:
    instrument: str
    quantity: float
    average_price: float
    # The broker's own live price for this instrument, when it has one (T212's real
    # /equity/positions response carries this alongside averagePricePaid — the same figure its
    # own app prices P&L off). Defaults to average_price for callers that don't have a live
    # quote (FakeBrokerClient), so a position's "current" value is at least its cost basis rather
    # than an arbitrary placeholder.
    current_price: float | None = None


class BrokerClient(ABC):
    @abstractmethod
    def submit_order(
        self, instrument: str, side: str, quantity: float, idempotency_key: str
    ) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError

    @abstractmethod
    def get_cash(self) -> float:
        raise NotImplementedError


class FakeBrokerClient(BrokerClient):
    """In-memory broker double: fills market orders instantly at a caller-supplied price,
    de-dupes on idempotency_key, and records every call for assertions. This de-dupe is a
    convenience for tests that call submit_order twice with the same key, not a claim about the
    real client: Trading212Client submits unconditionally (ADR-0014) — the actual retry-safety
    guard is the DB-level Order.idempotency_key unique constraint, upstream of either broker."""

    def __init__(self, starting_cash: float = 100_000.0, fill_price: float = 100.0):
        self.cash = starting_cash
        self.fill_price = fill_price
        self.positions: dict[str, BrokerPosition] = {}
        self._submitted_keys: dict[str, OrderResult] = {}
        self.calls: list[dict] = []

    def submit_order(self, instrument: str, side: str, quantity: float, idempotency_key: str) -> OrderResult:
        self.calls.append(
            {"instrument": instrument, "side": side, "quantity": quantity, "idempotency_key": idempotency_key}
        )
        if idempotency_key in self._submitted_keys:
            return self._submitted_keys[idempotency_key]  # retried request: no duplicate fill

        price = self.fill_price
        if side in ("buy", "add"):  # "add" (Volatility Harvester's add-on-weakness) buys more
            cost = price * quantity
            if cost > self.cash:
                result = OrderResult(broker_order_id=f"fake-{idempotency_key}", status="failed")
                self._submitted_keys[idempotency_key] = result
                return result
            self.cash -= cost
            existing = self.positions.get(instrument)
            if existing:
                total_qty = existing.quantity + quantity
                existing.average_price = (
                    existing.average_price * existing.quantity + price * quantity
                ) / total_qty
                existing.quantity = total_qty
            else:
                self.positions[instrument] = BrokerPosition(instrument, quantity, price)
        else:
            self.cash += price * quantity
            existing = self.positions.get(instrument)
            if existing:
                existing.quantity -= quantity
                if existing.quantity <= 0:
                    del self.positions[instrument]

        result = OrderResult(broker_order_id=f"fake-{idempotency_key}", status="filled", fill_price=price)
        self._submitted_keys[idempotency_key] = result
        return result

    def get_positions(self) -> list[BrokerPosition]:
        return list(self.positions.values())

    def get_cash(self) -> float:
        return self.cash
