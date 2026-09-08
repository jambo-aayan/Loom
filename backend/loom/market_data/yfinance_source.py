"""yfinance: a supplementary source for backtesting/backfill and instrument fundamentals
(P/E, dividend yield, debt ratios — for the Value/Quality Dip-Buyer, M2 scope) and sector/industry
classification (story 49, ADR-0008/0009). Never depended on for production/live order decisions —
Twelve Data (market_data/twelve_data.py) is the primary provider; this is the backfill/fundamentals
supplement the CLI backtest's acceptance criteria calls out."""

from __future__ import annotations

import math

from loom.fundamentals import FundamentalsProvider
from loom.market_data.base import MarketDataSource
from loom.strategy import Bar, InstrumentHistory


class YFinanceSource(MarketDataSource, FundamentalsProvider):
    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        import yfinance as yf

        ticker = yf.Ticker(instrument)
        df = ticker.history(start=start, end=end, interval="1d")
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
        return InstrumentHistory(instrument=instrument, bars=tuple(bars))

    def get_fundamentals(self, instrument: str) -> dict:
        """P/E, dividend yield, debt/equity, and sector/industry — used by the Value/Quality
        Dip-Buyer strategy (M2, ADR-0009 #5), not needed by any M1 strategy."""
        import yfinance as yf

        info = yf.Ticker(instrument).info
        return {
            "pe_ratio": info.get("trailingPE"),
            "dividend_yield": info.get("dividendYield"),
            "debt_to_equity": info.get("debtToEquity"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
        }
