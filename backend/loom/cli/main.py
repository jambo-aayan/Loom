"""Loom CLI: `loom backtest` (story 12, ticket #24) and `loom trade-pass` (story 12, ticket #25)."""

from __future__ import annotations

import json

import click
from sqlalchemy import select

from loom import calibration, db, killswitch, strategies  # noqa: F401  (registers strategies)
from loom.api.deps import get_broker, get_email_sender, get_insight_generator, get_market_data_source, get_push_sender
from loom.backtest.engine import run_backtest
from loom.config_versions import current_promoted
from loom.daily_loss import check_daily_loss_limit
from loom.insight.screening import run_screening_job
from loom.models import BacktestRun, Environment
from loom.models import Strategy as StrategyModel
from loom.notifications.dispatch import notify_daily_loss_limit, notify_failed_auto_approvals, notify_new_signals
from loom.reconciliation import manual_positions
from loom.seed import seed_all_strategies
from loom.settings import get_settings
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
    seed_all_strategies(session)

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
        strategy=strategy_cls.from_config(version.params),
        source=source,
        universe=resolved_universe,
        start=start,
        end=end,
        starting_capital=capital,
    )

    click.echo(json.dumps(result.stats, indent=2, default=str))
    click.echo(f"{len(result.trades)} trades over {len(result.equity_curve)} trading days.")

    run_id = None
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
        run_id = run.id
        click.echo(f"Saved backtest run {run.id}")

    calib = calibration.save_calibration(session, strategy_row.id, version.id, result.trades, run_id)
    click.echo(f"Confidence calibration: {len(calib.buckets)} bucket(s) from this run's closed trades.")


@cli.command("trade-pass")
@click.option("--environment", type=click.Choice(["demo", "live"]), default="demo", show_default=True)
@click.option("--universe", multiple=True)
def trade_pass(environment: str, universe: tuple[str, ...]):
    """Run one full fetch -> evaluate -> size -> execute trading pass (story 11)."""
    db.init_db()
    session = next(db.get_session())
    seed_all_strategies(session)

    env = Environment(environment)
    broker = get_broker(env)
    source = get_market_data_source()
    resolved_universe = list(universe) or getattr(source, "universe", lambda: ["VUSA.L", "VWRL.L", "TSLA", "NVDA"])()

    settings = get_settings()
    email_sender = get_email_sender()
    push_sender = get_push_sender()

    was_engaged = killswitch.is_engaged(env)
    breached, loss_pct = check_daily_loss_limit(session, env, broker)
    if breached and not was_engaged:
        killswitch.engage(session, env, actor="daily-loss-limit")
        notify_daily_loss_limit(email_sender, settings.notify_email, env, loss_pct)
        click.echo(f"Daily loss limit breached ({loss_pct:.2%}); kill switch engaged.")

    signals = run_trading_pass(env, session, broker, source, universe=resolved_universe)
    notify_new_signals(session, signals, push_sender, email_sender, settings.notify_email)
    notify_failed_auto_approvals(session, signals, env, email_sender, settings.notify_email)

    click.echo(f"Generated {len(signals)} signal(s) for {environment}:")
    for s in signals:
        click.echo(
            f"  [{s.status.value}] {s.action} {s.instrument} @ {s.reference_price:.2f} "
            f"(confidence {s.confidence:.2f})"
        )


@cli.command("screen-insights")
@click.option("--environment", type=click.Choice(["demo", "live"]), default="demo", show_default=True)
def screen_insights(environment: str):
    """The screening-tier Insight job (story 30, 52): runs on every signal candidate that
    doesn't have one yet. Its own job, deliberately separate from `trade-pass` — run it on its
    own schedule so a slow/costly LLM call never blocks order-related, rate-limit-sensitive work."""
    db.init_db()
    session = next(db.get_session())

    generator = get_insight_generator()
    created = run_screening_job(session, generator, environment=Environment(environment))
    click.echo(f"Generated {len(created)} screening Insight(s) for {environment}.")


@cli.command("reconcile")
@click.option("--environment", type=click.Choice(["demo", "live"]), default="demo", show_default=True)
def reconcile(environment: str):
    """Manual Book reconciliation (story 36, ticket #43): reports any broker position no
    strategy Book fully accounts for — surfaces what Overview already computes live, for
    visibility outside the dashboard."""
    db.init_db()
    session = next(db.get_session())

    env = Environment(environment)
    broker = get_broker(env)
    manual = manual_positions(session, env, broker)
    if not manual:
        click.echo(f"No untracked positions for {environment} — every broker position is accounted for.")
        return
    click.echo(f"{len(manual)} untracked position(s) for {environment}, attributed to Manual:")
    for snap in manual:
        click.echo(f"  {snap.instrument}: {snap.quantity:g} @ {snap.average_price:.2f}")


if __name__ == "__main__":
    cli()
