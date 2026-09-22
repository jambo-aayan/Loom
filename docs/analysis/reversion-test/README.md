# Reversion test harness

Throwaway analysis for ADR 0021 / ADR 0024, kept in the repo only because it has not been able to
run against real prices yet and will need to when it can. Not production code, not on any
strategy's import path. Findings: `docs/reversion-test-findings.md`.

```bash
cd docs/analysis/reversion-test
python run.py --source real --check-currency   # the production data stack
python run.py --source null-drift              # control: random walk, no reversion
python run.py --source null-zero               # control: driftless random walk
python run.py --source reverting               # positive control: reversion switched on
python run.py --source real --lag 1            # fill at the next close, not the signal close
```

Needs `TWELVE_DATA_API_KEY` for the primary source; falls through to yfinance backfill without
one, exactly as `PrimaryWithBackfillSource` does in production. Real fetches are cached under
`cache/` so a session with egress can produce the cache and a session without can still run the
measurement.

`out/` holds the runs from 2026-09-22, including `real.txt` / `real-stderr.txt` — the record of
the egress block that stopped the real-data run.
