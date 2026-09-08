from click.testing import CliRunner

from loom.cli.main import cli


def test_research_insights_reports_zero_when_nothing_eligible(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/cli_research.db")
    monkeypatch.setattr("loom.api.deps._fake_brokers", {})

    runner = CliRunner()
    result = runner.invoke(cli, ["research-insights", "--environment", "demo"])

    assert result.exit_code == 0, result.output
    assert "Generated 0 research Insight(s)" in result.output


def test_research_insights_generates_for_an_eligible_investment_style_signal(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/cli_research2.db")
    monkeypatch.setattr("loom.api.deps._fake_brokers", {})

    from loom import db as db_module
    from loom.models import (
        ApprovalMode,
        Book,
        ConfigVersionStatus,
        Environment,
        Signal,
        SignalStatus,
        SignalType,
        StrategyConfigVersion,
        StrategyStyle,
    )
    from loom.models import Strategy as StrategyModel

    db_module.init_db()
    session = next(db_module.get_session())
    strategy = StrategyModel(
        key="value_quality_dip_buyer",
        name="Value/Quality Dip-Buyer",
        style=StrategyStyle.investment,
        approval_mode=ApprovalMode.manual,
    )
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params={}
    )
    book = Book(strategy_id=strategy.id, environment=Environment.demo, name="Dip-Buyer · demo")
    session.add_all([config, book])
    session.flush()
    signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument="AAPL",
        signal_type=SignalType.entry,
        action="buy",
        confidence=0.9,
        exit_plan={"profit_target_pct": None, "stop_loss_pct": None, "time_exit_days": None},
        quantity=1,
        reference_price=100.0,
        status=SignalStatus.pending_approval,
    )
    session.add(signal)
    session.commit()
    db_module._engine = None
    db_module._SessionLocal = None

    runner = CliRunner()
    result = runner.invoke(cli, ["research-insights", "--environment", "demo"])

    assert result.exit_code == 0, result.output
    assert "Generated 1 research Insight(s)" in result.output
