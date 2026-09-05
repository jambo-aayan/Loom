# Twelve Data as primary market-data provider, yfinance as backtesting supplement

Trading 212's API provides no historical price/candle data — confirmed by research, it's a broker API, not a market-data API. Strategies need an external source for OHLC history to compute indicators. We chose Twelve Data as the primary provider (official Python client, covers US and LSE/UK listings, free tier of 800 calls/day is sufficient for a single-user daily/hourly-granularity bot), with yfinance kept as a free supplementary source for backtesting/backfill only — not a production dependency, since it's unofficial and has shown reliability issues (rate-limiting, breakage after site changes).

## Considered options

Alpha Vantage (free tier cut to 25 requests/day, no longer viable), IEX Cloud (shut down August 2024, dead), and Polygon.io (free tier is US-only, 15-minute-delayed, no LSE coverage) were all considered and rejected. Financial Modeling Prep is noted as a fallback if richer fundamentals are needed or Twelve Data's free tier is outgrown.
