from loom import auto_trading_gate


def test_disabled_by_default(session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "loom.auto_trading_gate.get_settings",
        lambda: type("S", (), {"auto_trading_gate_path": str(tmp_path / "auto_gate")})(),
    )

    assert auto_trading_gate.is_enabled() is False


def test_enable_and_disable_toggle_the_flag(session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "loom.auto_trading_gate.get_settings",
        lambda: type("S", (), {"auto_trading_gate_path": str(tmp_path / "auto_gate")})(),
    )

    auto_trading_gate.enable(session)
    assert auto_trading_gate.is_enabled() is True

    auto_trading_gate.disable(session)
    assert auto_trading_gate.is_enabled() is False
