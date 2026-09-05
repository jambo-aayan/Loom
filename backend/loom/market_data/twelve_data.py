"""Twelve Data client (ADR-0008, primary market-data provider). Not exercised in the default
test suite (network + a real API key) — see FixtureMarketDataSource for the faked boundary used
in tests and the CLI's zero-dependency default."""

from __future__ import annotations

import httpx

from loom.market_data.base import MarketDataSource
from loom.strategy import Bar, InstrumentHistory

BASE_URL = "https://api.twelvedata.com"


class TwelveDataSource(MarketDataSource):
    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=10.0)

    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        resp = self._client.get(
            "/time_series",
            params={
                "symbol": instrument,
                "interval": "1day",
                "start_date": start,
                "end_date": end,
                "apikey": self.api_key,
                "order": "ASC",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") == "error":
            raise RuntimeError(f"Twelve Data error for {instrument}: {payload.get('message')}")

        bars = tuple(
            Bar(
                date=row["datetime"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume") or 0.0),
            )
            for row in payload.get("values", [])
        )
        return InstrumentHistory(instrument=instrument, bars=bars)
