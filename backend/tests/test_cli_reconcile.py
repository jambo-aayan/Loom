from click.testing import CliRunner

from loom.cli.main import cli


def test_reconcile_reports_no_untracked_positions_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/cli_reconcile.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    # loom.api.deps._fake_brokers is a process-wide singleton, not reset between tests (a
    # pre-existing gap this reconciliation feature is the first to expose) — a leftover fill
    # from another test's demo broker would otherwise show up here as an untracked position.
    monkeypatch.setattr("loom.api.deps._fake_brokers", {})

    runner = CliRunner()
    result = runner.invoke(cli, ["reconcile", "--environment", "demo"])

    assert result.exit_code == 0, result.output
    assert "No untracked positions" in result.output


def test_reconcile_reports_an_untracked_broker_position(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/cli_reconcile2.db")
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )
    monkeypatch.setattr("loom.api.deps._fake_brokers", {})

    from loom.api.deps import get_broker
    from loom.execution.broker import BrokerPosition
    from loom.models import Environment

    get_broker(Environment.demo).positions["MSFT"] = BrokerPosition(instrument="MSFT", quantity=2, average_price=300.0)

    runner = CliRunner()
    result = runner.invoke(cli, ["reconcile", "--environment", "demo"])

    assert result.exit_code == 0, result.output
    assert "MSFT" in result.output
