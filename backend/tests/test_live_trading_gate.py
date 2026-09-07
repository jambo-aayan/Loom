from loom import live_trading_gate


def test_disabled_by_default(session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "loom.live_trading_gate.get_settings",
        lambda: type("S", (), {"live_trading_gate_path": str(tmp_path / "live_gate")})(),
    )

    assert live_trading_gate.is_enabled() is False


def test_enable_and_disable_toggle_the_flag(session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "loom.live_trading_gate.get_settings",
        lambda: type("S", (), {"live_trading_gate_path": str(tmp_path / "live_gate")})(),
    )

    live_trading_gate.enable(session)
    assert live_trading_gate.is_enabled() is True

    live_trading_gate.disable(session)
    assert live_trading_gate.is_enabled() is False
