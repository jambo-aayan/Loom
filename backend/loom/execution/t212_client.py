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
import math
import time

import httpx

from loom.execution.broker import BrokerClient, BrokerInstrument, BrokerPosition, OrderResult
from loom.execution.t212_tickers import StaticTickerMap, TickerMap, derive_loom_ticker

logger = logging.getLogger("loom.t212")


class Trading212ResponseError(RuntimeError):
    """A T212 response didn't match the shape this client expects — raised rather than silently
    defaulting to a placeholder value (e.g. treating an account with an unrecognized cash shape
    as having £0 available), since a wrong number here is a real-money mistake waiting to happen."""


# Statuses that mean an order won't change state on its own anymore — safe to stop polling.
# PARTIALLY_FILLED is deliberately included even though more could still happen: v1 doesn't model
# partial fills (see submit_order), so there's nothing more useful to wait for regardless.
_TERMINAL_ORDER_STATUSES = frozenset({"FILLED", "REJECTED", "CANCELLED", "PARTIALLY_FILLED"})


class Trading212Client(BrokerClient):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        client: httpx.Client | None = None,
        tickers: TickerMap | None = None,
    ):
        self.base_url = base_url
        self._client = client or httpx.Client(
            base_url=base_url, auth=httpx.BasicAuth(api_key, api_secret), timeout=15.0
        )
        # Injected rather than imported so the client needs no database session of its own
        # (ADR-0022). Production passes a DbTickerMap; the default keeps the pre-sync behaviour.
        self._tickers = tickers or StaticTickerMap()

    _MAX_ATTEMPTS = 4

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Paces off `x-ratelimit-*` headers after every response (so the *next* call already
        knows to slow down), and additionally retries with backoff when a call itself comes back
        429 — confirmed necessary against T212's real demo API: its window is tight enough
        (observed: limit=1, period=1s) that a request issued shortly after an unrelated prior call
        can still get rejected even though pacing looked fine going in, since pacing only reacts
        to the *previous* response's headers, not a live/racing rate-limit state."""
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            logger.info("t212 request %s %s params=%s json=%s", method, path, kwargs.get("params"), kwargs.get("json"))
            response = self._client.request(method, path, **kwargs)
            logger.info("t212 response %s %s -> %s %s", method, path, response.status_code, response.text[:500])
            if response.status_code == 429 and attempt < self._MAX_ATTEMPTS:
                if not self._pace_from_headers(response.headers):
                    time.sleep(1.0)
                continue
            self._pace_from_headers(response.headers)
            return response
        return response

    @staticmethod
    def _pace_from_headers(headers: httpx.Headers) -> bool:
        """`x-ratelimit-reset` is a Unix epoch timestamp for when the window resets, not a
        duration — sleeping on the raw header value (an earlier version of this did) means
        sleeping until some time in the 2080s, hanging the request indefinitely. Convert to a
        delta from now, and cap it: T212's per-endpoint windows are on the order of seconds
        (confirmed against a real response: limit=1, period=1s), so anything requesting a wait
        longer than that is itself a signal something's wrong with the header value, not a
        legitimate pace-back that's safe to block a live HTTP request on. Returns whether it
        actually paced (headers present and usable), so a 429 retry can fall back to a fixed
        delay when the response carries no usable rate-limit headers at all."""
        remaining = headers.get("x-ratelimit-remaining")
        reset_epoch = headers.get("x-ratelimit-reset")
        if remaining is not None and reset_epoch is not None:
            try:
                if int(remaining) <= 0:
                    delay = float(reset_epoch) - time.time()
                    time.sleep(min(max(0.0, delay), 30.0))
                return True
            except ValueError:
                return False
        return False

    def submit_order(self, instrument: str, side: str, quantity: float, idempotency_key: str) -> OrderResult:
        # T212 rejects a market order with more than 4 decimal places of quantity precision
        # ("invalid quantity precision 4", confirmed live) — our own sizing math produces full
        # float precision (account_value fractions, division by price), which routinely has far
        # more digits than that. Round down, never up: overshooting what risk/sizing actually
        # approved by a rounding error is the wrong direction to err in for a real-money order.
        rounded_quantity = math.floor(quantity * 10_000) / 10_000
        if rounded_quantity <= 0:
            # A small enough raw quantity (a high-priced instrument sized to a tiny fraction of
            # cash) rounds down to zero — sending that to T212 would just be a confusing 400
            # instead of a clean local failure. Same outcome as any other rejected order, no
            # network call needed to know it.
            return OrderResult(broker_order_id="", status="failed")
        response = self._request(
            "POST",
            "/equity/orders/market",
            json={
                "ticker": self._tickers.to_t212(instrument),
                "quantity": rounded_quantity if side in ("buy", "add") else -rounded_quantity,
            },
        )
        response.raise_for_status()
        payload = response.json()
        order_id = payload.get("id")
        status = str(payload.get("status", "")).upper()

        # A market order's synchronous POST response can come back "NEW" (filledQuantity=0) even
        # though it actually fills moments later — confirmed live: both orders in a real test
        # showed NEW here, then real positions/cash on T212 a few seconds afterward. Poll the
        # order briefly for a terminal state rather than recording a live fill as a failure.
        attempts = 0
        while status not in _TERMINAL_ORDER_STATUSES and attempts < 8:
            time.sleep(1.0)
            poll = self._request("GET", f"/equity/orders/{order_id}")
            if poll.status_code == 404:
                # No longer listed (some brokers drop a fully-settled order from this lookup) —
                # nothing more to learn by continuing to poll.
                break
            poll.raise_for_status()
            payload = poll.json()
            status = str(payload.get("status", "")).upper()
            attempts += 1

        # T212's order status is an uppercase lifecycle state (FILLED, NEW, PARTIALLY_FILLED,
        # REJECTED, CANCELLED, ...), not the lowercase "filled"/"failed" OrderResult.status
        # contract (broker.py) — normalize here, at the client boundary, same as the ticker
        # mapping. v1 doesn't model partial fills, so anything short of a full FILLED is "failed"
        # for now (a real distinction worth revisiting once that matters).
        # There's no top-level "fillPrice" in T212's real response — only filledQuantity and
        # filledValue (the executed monetary value); derive price from those instead of reading
        # a field that doesn't exist and would otherwise silently be None forever.
        filled_qty = payload.get("filledQuantity")
        filled_value = payload.get("filledValue")
        fill_price = filled_value / filled_qty if status == "FILLED" and filled_qty else None
        return OrderResult(
            broker_order_id=str(order_id),
            status="filled" if status == "FILLED" else "failed",
            fill_price=fill_price,
        )

    def get_positions(self) -> list[BrokerPosition]:
        response = self._request("GET", "/equity/positions")
        response.raise_for_status()
        # Confirmed live against a real, non-empty position (never exercised before — every
        # earlier test/real call happened to see an empty account): the ticker is nested under
        # "instrument", not top-level, and the price field is "averagePricePaid", not
        # "averagePrice". An empty-list response never exposed either mismatch.
        # T212's real response also carries "currentPrice" alongside averagePricePaid — its own
        # app prices P&L off this, not off any external market-data source. Loom's own P&L
        # display (loom/pnl.py) uses it in preference to Twelve Data's latest close, which is
        # daily/hourly-granularity history meant for strategy indicators (ADR-0008), not a live
        # quote, and visibly diverges from what the T212 app shows.
        return [
            BrokerPosition(
                instrument=self._tickers.from_t212(row["instrument"]["ticker"]),
                quantity=row["quantity"],
                average_price=row["averagePricePaid"],
                current_price=row.get("currentPrice"),
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

    # T212's own `type` values, mapped to the share/ETF distinction ADR-0019's cost model needs:
    # UK stamp duty applies to the purchase of a share and not to an ETF, and getting this wrong
    # misprices a round trip by 0.5%. Anything unrecognised becomes "other" rather than being
    # guessed into a bracket — a wrong cost is worse than a conservative unknown.
    _ASSET_TYPES = {
        "STOCK": "share",
        "EQUITY": "share",
        "ETF": "etf",
        "FUND": "etf",
    }

    def get_instruments(self) -> list[BrokerInstrument]:
        """Reads `GET /equity/metadata/instruments` — a multi-thousand-row response, which is why
        ADR-0022 syncs it on a schedule into the `instruments` table rather than calling it per
        order.

        NOTE: the field names below are T212's documented shape but have NOT been exercised
        against a live response in this codebase yet. Every field except the ticker is read
        defensively so an unexpected shape degrades to a usable row rather than an exception, and
        a row whose venue `derive_loom_ticker` cannot name is skipped rather than stored under a
        guessed Loom ticker. If the shape turns out to differ, this method is the only place that
        needs to change — everything downstream works against `BrokerInstrument`."""
        response = self._request("GET", "/equity/metadata/instruments")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise Trading212ResponseError(
                f"unexpected /equity/metadata/instruments shape, expected a list: {payload!r:.300}"
            )

        instruments: list[BrokerInstrument] = []
        skipped = 0
        for row in payload:
            if not isinstance(row, dict):
                skipped += 1
                continue
            t212_ticker = row.get("ticker")
            if not t212_ticker:
                skipped += 1
                continue
            loom_ticker = derive_loom_ticker(t212_ticker, row.get("shortName"))
            if loom_ticker is None:
                skipped += 1  # a venue we cannot name confidently; see derive_loom_ticker
                continue
            raw_type = str(row.get("type") or "").upper()
            instruments.append(
                BrokerInstrument(
                    loom_ticker=loom_ticker,
                    t212_ticker=t212_ticker,
                    name=str(row.get("name") or row.get("shortName") or loom_ticker),
                    currency=str(row.get("currencyCode") or ""),
                    asset_type=self._ASSET_TYPES.get(raw_type, "other"),
                    exchange=row.get("exchange") or None,
                    isin=row.get("isin") or None,
                    min_trade_quantity=_optional_float(row.get("minTradeQuantity")),
                )
            )

        logger.info("t212 instruments: %d usable, %d skipped", len(instruments), skipped)
        return instruments


def _optional_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
