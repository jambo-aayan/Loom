"""Twelve Data client (primary for US listings only, decision D25: the free tier doesn't cover LSE
listings). Not exercised against the network in the test suite; see FixtureMarketDataSource for the
faked boundary used in tests and the CLI's zero-dependency default.

Every request names the listing's exchange as well as its symbol: a bare "VUSA" resolves to a
Munich or XETRA line priced in EUR. The currency Twelve Data reports in `meta.currency` is passed
through untouched for loom.market_data.boundary.normalise to check.
"""

from __future__ import annotations

import math

import httpx

from loom.instruments import Instrument
from loom.market_data.boundary import RawHistory
from loom.strategy import Bar

BASE_URL = "https://api.twelvedata.com"


class TwelveDataSource:
    name = "twelve_data"

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=10.0)

    def fetch_daily(self, instrument: Instrument, start: str, end: str) -> RawHistory:
        resp = self._client.get(
            "/time_series",
            params={
                "symbol": instrument.twelve_data_symbol,
                "exchange": instrument.exchange.value,
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
            raise RuntimeError(f"Twelve Data error for {instrument.id}: {payload.get('message')}")

        bars = []
        for row in payload.get("values", []):
            open_, high, low, close = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            # A live feed can hand back a gap/glitch day (NaN or inf) that a strategy's stats
            # (e.g. statistics.pstdev) will choke on in a confusing way far from this source —
            # drop it here instead, at the boundary, same as any other malformed external input.
            if not all(math.isfinite(v) for v in (open_, high, low, close)):
                continue
            volume = float(row.get("volume") or 0.0)
            bars.append(Bar(date=row["datetime"], open=open_, high=high, low=low, close=close, volume=volume))
        return RawHistory(
            symbol=f"{instrument.twelve_data_symbol}:{instrument.exchange.value}",
            reported_unit=(payload.get("meta") or {}).get("currency"),
            bars=tuple(bars),
        )
