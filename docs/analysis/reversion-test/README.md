# Reversion test harness

Throwaway analysis for ADR 0021 / ADR 0024, kept in the repo because the measurement it produced
is what ADR 0025 rests on. Not production code, not on any strategy's import path.
Findings: `docs/reversion-test-findings.md`.

## It has run

Prices are committed at `prices/daily_2018-01-01_2026-09-22.json` — all 22 candidates, Yahoo,
2018-01-02..2026-09-18, ~2,200 bars each, every one a sterling (`GBp`/`GBP`) line. `run.py
--source real` prefers that file over a live fetch, so the measurement reproduces in any session,
including one with no network:

```bash
cd docs/analysis/reversion-test
python run.py --source real --check-currency --lag 0
python run.py --source real --check-currency --lag 1
```

`--check-currency` is the only part that needs egress (it re-reads each line's currency from
Yahoo); without it the committed file's recorded currency is used and still flagged.

Two supplementary scripts back up numbers in the findings that `run.py` does not print:
`extra.py` (trade economics, per-year edge with 2020/2022 removed, the bootstrapped
Deep − Steady difference) and `blocks.py` (the edge interval under three blocking schemes, since
the 22 tickers are not 22 independent series). Their output is in `out/`.

## Re-fetching the prices

The session this harness was *built* in could not reach any price provider. If a future session
hits the same wall, three ways round it, cheapest first.

### 1. Fetch the prices anywhere else and commit them (no settings change)

`fetch_prices.py` is standalone — it imports nothing from `loom` and needs only `yfinance`. Run
it on a laptop, in CI, or in any session with egress:

```bash
pip install yfinance
cd docs/analysis/reversion-test
python fetch_prices.py                  # writes prices/daily_2018-01-01_<today>.json
git add prices/ && git commit -m "Add price cache for the reversion test"
```

`run.py --source real` prefers a committed price file over a live fetch, so the measurement then
runs anywhere, including a session with no network. The file stores each instrument's reported
currency next to its bars, so the GBP-vs-USD line check is captured by the machine that could
actually see the provider, and the harness re-flags any non-GBP line on every run.

### 2. Allow the hosts on the cloud environment

In the environment editor at claude.ai/code, set **Network access** to **Custom**, tick **Also
include default list of common package managers**, and list:

```text
*.yahoo.com
api.twelvedata.com
```

Yahoo needs the wildcard: yfinance touches `fc.yahoo.com` and `guce.yahoo.com` for cookies before
`query1/query2.finance.yahoo.com`. Put `TWELVE_DATA_API_KEY` in the same dialog's **Environment
variables** if using the primary provider — `sources.py` reads it.

An **API credential** on the environment would also reach the host without changing the access
level, and keeps the key out of the session entirely. It doesn't fit Twelve Data as things
stand, because the key travels as a `apikey=` query parameter rather than a header.

### 3. Teleport and run locally

`claude --teleport <session-id>` from a checkout, then run the harness with the machine's own
network.

## Running it

```bash
cd docs/analysis/reversion-test
python run.py --source real --check-currency   # committed prices, else the production stack
python run.py --source null-drift              # control: random walk, no reversion
python run.py --source null-zero               # control: driftless random walk
python run.py --source reverting               # positive control: reversion switched on
python run.py --source real --lag 1            # fill at the next close, not the signal close
```

`out/` holds the runs from 2026-09-22: `real-lag0.txt` / `real-lag1.txt` are the real-data
measurement, the three `null-*` / `reverting` files are the controls they are read against, and
`real.txt` / `real-stderr.txt` are kept as the record of the egress block that stopped the first
attempt.

## A gotcha in the primary provider

`loom/market_data/twelve_data.py` does not pass `outputsize` to `/time_series`. Twelve Data
defaults that to 30 rows **even when `start_date` and `end_date` are set**, so a multi-year range
request comes back as roughly a month of bars, silently. That affects any backtest on the primary
provider, not just this analysis. `fetch_prices.py` passes `outputsize=5000` for its own fetches;
fixing the source itself is production code and wants a spec and ticket.
