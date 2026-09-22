"""Where the bars come from.

`real` is the production stack, unchanged: TwelveDataSource primary, YFinanceSource backfill,
wired through PrimaryWithBackfillSource exactly as loom/api/deps.py wires it.

`null-drift` / `null-zero` are controls, not data. They reuse the repo's own
FixtureMarketDataSource — a plain geometric random walk with *no* reversion in the generator.
That is the point: whatever the two entry rules score on a process that cannot revert is the
score that means "nothing here". Any real-data number has to beat it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND = Path("/home/user/Loom/backend")
sys.path.insert(0, str(BACKEND))

from loom.strategy import Bar, InstrumentHistory  # noqa: E402

from universe import BUCKET, NULL_PROFILE, NULL_START_PRICE  # noqa: E402

CACHE = Path(__file__).parent / "cache"
PRICES = Path(__file__).parent / "prices"


def real_source():
    from loom.market_data.composite import PrimaryWithBackfillSource
    from loom.market_data.twelve_data import TwelveDataSource
    from loom.market_data.yfinance_source import YFinanceSource

    return PrimaryWithBackfillSource(
        TwelveDataSource(api_key=os.environ.get("TWELVE_DATA_API_KEY", "")),
        YFinanceSource(),
    )


def null_source(zero_drift: bool = False):
    from loom.market_data.fixture import FixtureMarketDataSource

    profiles = {}
    for ticker, bucket in BUCKET.items():
        drift, vol = NULL_PROFILE[bucket]
        profiles[ticker] = (NULL_START_PRICE[bucket], 0.0 if zero_drift else drift, vol)
    return FixtureMarketDataSource(profiles=profiles)


def load(source_name: str, tickers: list[str], start: str, end: str) -> dict[str, InstrumentHistory]:
    """Fetch (or read from cache) one history per ticker. Tickers that come back empty or error
    are reported by the caller rather than silently dropped — an unresolvable ticker is a finding.
    """
    if source_name == "real":
        # A committed price file wins over a live fetch: it is the whole point of fetch_prices.py
        # that a machine with egress can produce one and any session can then run the
        # measurement, this one included.
        committed = sorted(PRICES.glob("daily_*.json")) if PRICES.exists() else []
        if committed:
            raw = json.loads(committed[-1].read_text())
            meta = raw.get("meta", {})
            print(f"  using committed prices: {committed[-1].name} "
                  f"(provider={meta.get('provider')}, fetched={meta.get('fetched')})", file=sys.stderr)
            out = {}
            for t, rec in raw["instruments"].items():
                cur = rec.get("currency")
                if cur not in ("GBp", "GBP", None):
                    print(f"  {t:8s} WARNING: currency is {cur}, not a GBP line", file=sys.stderr)
                out[t] = InstrumentHistory(instrument=t, bars=tuple(Bar(**b) for b in rec["bars"]))
            return out

        CACHE.mkdir(exist_ok=True)
        cache_file = CACHE / f"real_{start}_{end}.json"
        if cache_file.exists():
            raw = json.loads(cache_file.read_text())
            return {
                t: InstrumentHistory(instrument=t, bars=tuple(Bar(**b) for b in bars))
                for t, bars in raw.items()
            }
        src = real_source()
        out, dump = {}, {}
        for t in tickers:
            try:
                h = src.get_history(t, start, end)
            except Exception as exc:  # noqa: BLE001 — an unfetchable ticker is a result, not a crash
                print(f"  {t:8s} FETCH FAILED: {type(exc).__name__}: {str(exc)[:110]}", file=sys.stderr)
                continue
            if not h.bars:
                print(f"  {t:8s} resolved to zero bars", file=sys.stderr)
                continue
            out[t] = h
            dump[t] = [vars(b) for b in h.bars]
            print(f"  {t:8s} {len(h.bars):5d} bars  {h.bars[0].date} .. {h.bars[-1].date}", file=sys.stderr)
        if dump:
            cache_file.write_text(json.dumps(dump))
        return out

    if source_name == "reverting":
        from reverting import RevertingSource

        src = RevertingSource()
        return {t: src.get_history(t, start, end) for t in tickers}

    src = null_source(zero_drift=(source_name == "null-zero"))
    return {t: src.get_history(t, start, end) for t in tickers}


def currency_of(ticker: str) -> str | None:
    """The GBP-vs-USD-line check docs/compounder-universe-candidates.md warns about. LSE GBP
    lines quote in pence and report 'GBp'; a 'USD' here is the USD line, and picking it
    reinstates the 0.15%-each-way FX cost that the whole design exists to avoid.
    """
    try:
        import yfinance as yf

        return yf.Ticker(ticker).fast_info.get("currency")
    except Exception:  # noqa: BLE001
        return None
