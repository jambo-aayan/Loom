"""yfinance: the primary price source for LSE listings (decision D25: Twelve Data's free tier
doesn't cover them, and the research used Yahoo bars), the fallback for US listings, and the source
of instrument fundamentals (P/E, dividend yield, debt ratios, sector) for the Crash-buyer.

Unofficial and fragile: callers must never act on its data without the freshness check
(loom.market_data.freshness). The currency Yahoo reports for the listing is passed through
untouched for loom.market_data.boundary.normalise to check.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from loom.fundamentals import FundamentalsProvider
from loom.instruments import Instrument, get_instrument
from loom.market_data.boundary import RawHistory
from loom.strategy import Bar


class YFinanceSource(FundamentalsProvider):
    name = "yahoo"

    def fetch_daily(self, instrument: Instrument, start: str, end: str) -> RawHistory:
        import yfinance as yf

        ticker = yf.Ticker(instrument.yahoo_symbol)
        # yfinance's `end` is exclusive; Loom's contract (MarketDataSource.get_history) is inclusive.
        exclusive_end = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
        df = ticker.history(start=start, end=exclusive_end, interval="1d")
        bars = []
        for index, row in df.iterrows():
            open_, high, low, close = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            # Same reasoning as TwelveDataSource: drop a bad/gap day at the boundary rather than
            # let a NaN/inf close silently break a strategy's stats far from where it came from.
            if not all(math.isfinite(v) for v in (open_, high, low, close)):
                continue
            bars.append(
                Bar(
                    date=index.date().isoformat(),
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=float(row.get("Volume", 0.0)),
                )
            )
        metadata = getattr(ticker, "history_metadata", None) or {}
        return RawHistory(symbol=instrument.yahoo_symbol, reported_unit=metadata.get("currency"), bars=tuple(bars))

    def get_fundamentals(self, instrument: str) -> dict:
        """P/E, dividend yield, debt/equity, and sector/industry — used by the Value/Quality
        Dip-Buyer strategy (M2, ADR-0009 #5), not needed by any M1 strategy."""
        import yfinance as yf

        info = yf.Ticker(get_instrument(instrument).yahoo_symbol).info
        return {
            "pe_ratio": info.get("trailingPE"),
            "dividend_yield": info.get("dividendYield"),
            "debt_to_equity": info.get("debtToEquity"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }
