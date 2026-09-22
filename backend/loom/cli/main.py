"""Loom CLI: `loom backtest` (story 12, ticket #24) and `loom trade-pass` (story 12, ticket #25)."""

from __future__ import annotations

import json

import click
from sqlalchemy import select

from loom import calibration, db, killswitch, logging_config, strategies  # noqa: F401  (registers strategies)
from loom.api.deps import (
    get_broker,
    get_email_sender,
    get_market_data_source,
    get_push_sender,
    get_research_generator,
    get_screening_generator,
)
from loom.backtest.engine import run_backtest
from loom.config_versions import current_promoted
from loom.daily_loss import check_daily_loss_limit
from loom.insight.research import run_research_job
from loom.insight.screening import run_screening_job
from loom.models import BacktestRun, Environment
from loom.models import Strategy as StrategyModel
from loom.notifications.dispatch import (
    notify_daily_loss_limit,
    notify_exit_executed,
    notify_failed_auto_approvals,
    notify_new_signals,
)
from loom.config_versions import duplicate_version_numbers
from loom.exit_pass import run_exit_pass
from loom.instruments import sync_instruments
from loom.reconciliation import manual_positions
from loom.seed import seed_all_strategies
from loom.settings import get_settings
from loom.trading_pass import STRATEGY_REGISTRY, run_trading_pass

logging_config.configure()


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

    was_engaged = killswitch.is_engaged(session, env)
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

    generator = get_screening_generator()
    created = run_screening_job(session, generator, environment=Environment(environment))
    click.echo(f"Generated {len(created)} screening Insight(s) for {environment}.")


@cli.command("research-insights")
@click.option("--environment", type=click.Choice(["demo", "live"]), default="demo", show_default=True)
def research_insights(environment: str):
    """The automatic, free-tier research pass (story 52, ADR-0013, ticket #48): sweeps
    investment-style signals already at pending_approval/auto_approved that don't have research
    commentary yet. The paid Sonnet tier is exclusively user-triggered from the dashboard — never
    reachable from this or any other automatic job."""
    db.init_db()
    session = next(db.get_session())

    generator = get_research_generator()
    created = run_research_job(session, generator, environment=Environment(environment))
    click.echo(f"Generated {len(created)} research Insight(s) for {environment}.")


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


@cli.command("exit-pass")
@click.option("--environment", type=click.Choice(["demo", "live"]), default="demo", show_default=True)
def exit_pass(environment: str):
    """Evaluate every open Position carrying an Exit plan (#53, ADR-0018).

    Runs far more often than the entry pass: entries are patient by design, exits are not. In dry
    run it records what it would have done and sells nothing — those records are the first
    feedback any exit parameter in the roster has ever had (gap analysis D0).
    """
    db.init_db()
    session = next(db.get_session())
    seed_all_strategies(session)

    env = Environment(environment)
    decisions = run_exit_pass(env, session, get_broker(env), get_market_data_source())

    # Outside the pass, matching how the trading pass notifies: delivery is a side effect the
    # call site opts into, not something baked into the state machine.
    executed_ids = [d.executed_signal_id for d in decisions if d.executed_signal_id]
    if executed_ids:
        notify_exit_executed(
            session, executed_ids, env, get_push_sender(), get_email_sender(), get_settings().notify_email
        )

    if not decisions:
        click.echo(f"No positions would have exited for {environment}.")
        return

    verb = "exited" if executed_ids else "would have exited (dry run — nothing sold)"
    click.echo(f"{len(decisions)} position(s) {verb} for {environment}:")
    for d in decisions:
        held = f", held {d.hold_days}d" if d.hold_days is not None else ""
        click.echo(f"  {d.instrument}: {d.exit_reason} @ {d.decision_price:.2f}{held}")


@cli.command("sync-instruments")
@click.option("--environment", type=click.Choice(["demo", "live"]), default="demo", show_default=True)
def sync_instruments_cmd(environment: str):
    """Sync Trading 212's instrument metadata into the instruments table (ADR-0022).

    This is what lets Loom trade anything beyond the four hardcoded tickers, and it is where an
    instrument's currency and asset type come from — which ADR-0019's cost model needs to know
    whether FX conversion and UK stamp duty apply. Metadata changes rarely, so this belongs on a
    slow schedule rather than on the path of an order.
    """
    db.init_db()
    session = next(db.get_session())
    env = Environment(environment)

    result = sync_instruments(session, get_broker(env, session=session))
    click.echo(
        f"{result.total} instrument(s) for {environment}: "
        f"{result.added} added, {result.updated} updated, {result.unchanged} unchanged."
    )
    for conflict in result.conflicts:
        click.echo(f"  conflict (skipped): {conflict}")
    if result.conflicts:
        click.echo(
            f"{len(result.conflicts)} instrument(s) skipped — two T212 tickers derived the same "
            "Loom ticker. Storing either would make positions ambiguous."
        )


@cli.command("check-config-versions")
def check_config_versions():
    """Reports strategies carrying more than one promoted config version under the same number
    (#61). Reports only — it never renumbers, since the changelog exists to be traceable and
    rewriting it is a human's decision."""
    db.init_db()
    session = next(db.get_session())

    duplicates = duplicate_version_numbers(session)
    if not duplicates:
        click.echo("No duplicate promoted version numbers — config version history is clean.")
        return

    click.echo(f"{len(duplicates)} duplicated promoted version number(s):")
    for row in duplicates:
        click.echo(f"  {row['strategy_key']}: version {row['version_number']} promoted {row['count']} times")
    click.echo(
        "\nNothing was changed. Each Signal references its config version by id, so attribution is "
        "intact; what a duplicate breaks is reading the changelog. Decide per strategy whether to "
        "renumber or leave the history as it happened."
    )


if __name__ == "__main__":
    cli()
