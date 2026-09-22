"""Fetch the candidate universe's daily bars and write the file the harness reads.

Standalone on purpose: it imports nothing from `loom`, so it runs on a laptop, in CI, or in any
session that has egress, without the backend installed. Only needs `pip install yfinance`.

    python fetch_prices.py                      # writes prices/daily_2018-01-01_<today>.json
    python fetch_prices.py --provider twelvedata --api-key $TWELVE_DATA_API_KEY

Commit the result. `run.py --source real` picks it up and the measurement runs anywhere,
including a session with no network at all.

The file records each instrument's reported currency alongside its bars, so the GBP-vs-USD line
check that docs/compounder-universe-candidates.md warns about is captured at fetch time by the
machine that could actually see the provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from universe import TICKERS

OUT_DIR = Path(__file__).parent / "prices"


def fetch_yahoo(ticker: str, start: str, end: str):
    import yfinance as yf

    t = yf.Ticker(ticker)
    df = t.history(start=start, end=end, interval="1d")
    try:
        currency = t.fast_info.get("currency")
    except Exception:  # noqa: BLE001
        currency = None
    bars = [
        {
            "date": idx.date().isoformat(),
            "open": float(r["Open"]),
            "high": float(r["High"]),
            "low": float(r["Low"]),
            "close": float(r["Close"]),
            "volume": float(r.get("Volume", 0.0) or 0.0),
        }
        for idx, r in df.iterrows()
        if all(v == v for v in (r["Open"], r["High"], r["Low"], r["Close"]))  # drop NaN days
    ]
    return bars, currency


def fetch_twelvedata(ticker: str, start: str, end: str, api_key: str):
    import httpx

    # outputsize matters: Twelve Data defaults to 30 rows even when start_date/end_date are set,
    # so a range request without it silently returns a month. loom's TwelveDataSource does not
    # pass it — see the note in docs/reversion-test-findings.md.
    resp = httpx.get(
        "https://api.twelvedata.com/time_series",
        params={"symbol": ticker, "interval": "1day", "start_date": start, "end_date": end,
                "apikey": api_key, "order": "ASC", "outputsize": 5000},
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") == "error":
        raise RuntimeError(payload.get("message"))
    bars = [
        {"date": r["datetime"], "open": float(r["open"]), "high": float(r["high"]),
         "low": float(r["low"]), "close": float(r["close"]), "volume": float(r.get("volume") or 0.0)}
        for r in payload.get("values", [])
    ]
    return bars, payload.get("meta", {}).get("currency")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="yahoo", choices=["yahoo", "twelvedata"])
    ap.add_argument("--api-key", default="")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default=date.today().isoformat())
    args = ap.parse_args()

    if args.provider == "twelvedata" and not args.api_key:
        sys.exit("--provider twelvedata needs --api-key")

    out = {"meta": {"provider": args.provider, "start": args.start, "end": args.end,
                    "fetched": date.today().isoformat()}, "instruments": {}}

    print(f"{'ticker':9s} {'bars':>6s}  {'from':10s} {'to':10s}  currency")
    print("-" * 56)
    for t in TICKERS:
        try:
            bars, currency = (fetch_yahoo(t, args.start, args.end) if args.provider == "yahoo"
                              else fetch_twelvedata(t, args.start, args.end, args.api_key))
        except Exception as exc:  # noqa: BLE001 — an unfetchable ticker is a result, not a crash
            print(f"{t:9s} FAILED: {type(exc).__name__}: {str(exc)[:60]}")
            continue
        if not bars:
            print(f"{t:9s} {0:6d}  (no data — ticker does not resolve)")
            continue
        flag = "" if currency in ("GBp", "GBP") else "   <-- NOT A GBP LINE"
        print(f"{t:9s} {len(bars):6d}  {bars[0]['date']} {bars[-1]['date']}  {str(currency):8s}{flag}")
        out["instruments"][t] = {"currency": currency, "bars": bars}

    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"daily_{args.start}_{args.end}.json"
    path.write_text(json.dumps(out))
    print(f"\nwrote {path}  ({len(out['instruments'])}/{len(TICKERS)} resolved)")
    print("Commit it, then: python run.py --source real")


if __name__ == "__main__":
    main()
