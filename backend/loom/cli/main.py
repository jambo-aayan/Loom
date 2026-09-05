"""Loom CLI: `loom backtest` (story 12, ticket #24) and `loom trade-pass` (story 12, ticket #25)."""

from __future__ import annotations

import json

import click
from sqlalchemy import select

from loom import db, strategies  # noqa: F401  (registers strategies)
from loom.api.deps import get_broker, get_market_data_source
from loom.backtest.engine import run_backtest
from loom.config_versions import current_promoted
from loom.models import BacktestRun, Environment
from loom.models import Strategy as StrategyModel
from loom.seed import seed_low_vol_compounder
from loom.strategy import StrategyConfig
from loom.trading_pass import STRATEGY_REGISTRY, run_trading_pass


@click.group()
def cli():
    """Loom: systematic Trading 212 trading bot."""


@cli.command()
@click.option("--strategy", "strategy_key", default="low_vol_compounder", show_default=True)
@click.option("--universe", multiple=True, help="Instrument tickers; defaults to the fixture universe.")
@click.option("--start", required=True)
@click.option("--end", required=True)
@click.option("--capital", default=10_000.0, show_default=True)
@click.option("--save/--no-save", default=True, help="Persist the run to the database.")
def backtest(strategy_key: str, universe: tuple[str, ...], start: str, end: str, capital: float, save: bool):
    """Backtest a strategy from the CLI, "in seconds", against the bundled fixture data by
    default (story 41) or a real Twelve Data key if configured."""
    db.init_db()
    session = next(db.get_session())
    seed_low_vol_compounder(session)

    strategy_row = session.execute(select(StrategyModel).where(StrategyModel.key == strategy_key)).scalar_one_or_none()
    if strategy_row is None:
        raise click.ClickException(f"unknown strategy {strategy_key!r}")
    version = current_promoted(session, strategy_row.id)
    if version is None:
        raise click.ClickException(f"strategy {strategy_key!r} has no promoted config version")

    strategy_cls = STRATEGY_REGISTRY[strategy_key]
    source = get_market_data_source()
    resolved_universe = list(universe) or getattr(source, "universe", lambda: ["VUSA.L", "VWRL.L", "TSLA", "NVDA"])()

    result = run_backtest(
        strategy=strategy_cls(StrategyConfig(params=version.params)),
        source=source,
        universe=resolved_universe,
        start=start,
        end=end,
        starting_capital=capital,
    )

    click.echo(json.dumps(result.stats, indent=2, default=str))
    click.echo(f"{len(result.trades)} trades over {len(result.equity_curve)} trading days.")

    if save:
        run = BacktestRun(
            strategy_id=strategy_row.id,
            config_version_id=version.id,
            name=f"{strategy_row.name} {start}..{end}",
            universe=resolved_universe,
            start_date=start,
            end_date=end,
            starting_capital=capital,
            results=result.as_dict(),
        )
        session.add(run)
        session.commit()
        click.echo(f"Saved backtest run {run.id}")


@cli.command("trade-pass")
@click.option("--environment", type=click.Choice(["demo", "live"]), default="demo", show_default=True)
@click.option("--universe", multiple=True)
def trade_pass(environment: str, universe: tuple[str, ...]):
    """Run one full fetch -> evaluate -> size -> execute trading pass (story 11)."""
    db.init_db()
    session = next(db.get_session())
    seed_low_vol_compounder(session)

    env = Environment(environment)
    broker = get_broker(env)
    source = get_market_data_source()
    resolved_universe = list(universe) or getattr(source, "universe", lambda: ["VUSA.L", "VWRL.L", "TSLA", "NVDA"])()

    signals = run_trading_pass(env, session, broker, source, universe=resolved_universe)
    click.echo(f"Generated {len(signals)} signal(s) for {environment}:")
    for s in signals:
        click.echo(
            f"  [{s.status.value}] {s.action} {s.instrument} @ {s.reference_price:.2f} "
            f"(confidence {s.confidence:.2f})"
        )


if __name__ == "__main__":
    cli()
