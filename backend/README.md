# Loom backend

Shared Python core (domain models, `Strategy` interface, risk/sizing, execution/Trading 212
client, persistence) consumed by two entrypoints — the CLI and the FastAPI service — plus
Alembic migrations for Neon Postgres. See `../CONTEXT.md`, `../docs/adr/`, and GitHub issue #1
for the domain model and spec this implements.

## Local dev

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env   # optional — every value has a safe local-dev fallback
```

Zero external credentials are required for local dev: with no `.env`, the app falls back to a
sqlite file DB, an in-memory fake Trading 212 broker, bundled synthetic (fixture) market data,
and canned Insight commentary instead of a real Anthropic call (`loom/api/deps.py`,
`loom/settings.py`). Set the real env vars (see `.env.example`) to point at Neon, real Trading
212 Demo/Live keys, Twelve Data, and Anthropic once you have them.

### Run migrations

```bash
alembic upgrade head
```

Works identically against `DATABASE_URL=sqlite:///./loom_dev.db` (the default) or a real Neon
Postgres connection string — the URL is read from `loom.settings.get_settings()`, not hardcoded
in `alembic.ini`.

### Run the API

```bash
uvicorn loom.api.main:app --reload --port 8000
```

Seeds the Low-Vol Compounder strategy with a promoted v1 config on first startup. Interactive
docs at `http://localhost:8000/docs`.

### CLI

```bash
loom backtest --start 2023-01-02 --end 2023-06-30          # story 41: runs in seconds, no keys needed
loom trade-pass --environment demo                          # story 11/12
```

### Tests, lint, types

```bash
pytest                # 37 tests: strategy contract, backtest engine (no-lookahead), risk/sizing,
                       # kill switch, trading pass, approval pipeline via real HTTP (FastAPI
                       # TestClient), counterfactual simulation, config version lifecycle
ruff check loom tests
mypy loom
```

## Layout

```
loom/
  models.py            # Signal, Order, Position, Strategy, Book, Environment, StrategyConfigVersion, ...
  strategy.py           # the pluggable Strategy interface + contract
  strategies/            # concrete strategies (Low-Vol Compounder in M1; roster grows in M2)
  risk.py                # risk/sizing layer, shared by live trading and backtesting
  killswitch.py           # local flag file, checked before every order submission
  trading_pass.py          # run_trading_pass(); approve/reject/execute — the shared safety path
  execution/                # broker interface + FakeBrokerClient (tests) + Trading212Client (real)
  market_data/                # market data interface + FixtureMarketDataSource + TwelveDataSource
  backtest/                    # simulated portfolio/fill engine + counterfactual simulation
  insight/                      # LLM screening tier (FakeInsightGenerator / AnthropicInsightGenerator)
  config_versions.py             # draft -> promoted lifecycle, param diffing
  api/                             # FastAPI service (routers, schemas, DI)
  cli/                              # `loom backtest`, `loom trade-pass`
alembic/                             # migrations
tests/
```
