"""Confirms `loom trade-pass` dispatches notifications the same way the API's
/trading-pass/run endpoint does (story: M3 CLI parity)."""

from click.testing import CliRunner

from loom.cli.main import cli


def test_trade_pass_emails_pending_signals(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/cli_trade_pass.db")

    runner = CliRunner()
    result = runner.invoke(cli, ["trade-pass", "--environment", "demo"])

    assert result.exit_code == 0, result.output

    from loom.api.deps import get_email_sender

    assert len(get_email_sender().sent) > 0
