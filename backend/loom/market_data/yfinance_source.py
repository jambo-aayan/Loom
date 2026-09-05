"""yfinance: a supplementary source for backtesting/backfill and instrument fundamentals
(P/E, dividend yield, debt ratios — for the Value/Quality Dip-Buyer, M2 scope) and sector/industry
classification (story 49, ADR-0008/0009). Never depended on for production/live order decisions —
Twelve Data (market_data/twelve_data.py) is the primary provider; this is the backfill/fundamentals
supplement the CLI backtest's acceptance criteria calls out."""

from __future__ import annotations

from loom.fundamentals import FundamentalsProvider
from loom.market_data.base import MarketDataSource
from loom.strategy import Bar, InstrumentHistory


class YFinanceSource(MarketDataSource, FundamentalsProvider):
    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        import yfinance as yf

        ticker = yf.Ticker(instrument)
        df = ticker.history(start=start, end=end, interval="1d")
        bars = tuple(
            Bar(
                date=index.date().isoformat(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0.0)),
            )
            for index, row in df.iterrows()
        )
        return InstrumentHistory(instrument=instrument, bars=bars)

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
