import pytest

from loom import db


@pytest.fixture()
def session():
    db.init_db("sqlite:///:memory:")
    gen = db.get_session()
    s = next(gen)
    yield s
    try:
        next(gen)
    except StopIteration:
        pass


@pytest.fixture(autouse=True)
def _gates_open_by_default(tmp_path, monkeypatch):
    """The global auto-trading/live-trading gates (CONTEXT.md) default OFF in production
    settings, but most of this suite predates them and assumes auto-approval and live-environment
    order submission just work. Default both gates to enabled here so those tests don't need
    updating one-by-one; a test that specifically exercises gate-off behavior overrides
    get_settings itself, which wins over this autouse fixture."""
    auto_path = tmp_path / "auto_trading_gate"
    live_path = tmp_path / "live_trading_gate"
    auto_path.touch()
    live_path.touch()
    monkeypatch.setattr(
        "loom.auto_trading_gate.get_settings",
        lambda: type("S", (), {"auto_trading_gate_path": str(auto_path)})(),
    )
    monkeypatch.setattr(
        "loom.live_trading_gate.get_settings",
        lambda: type("S", (), {"live_trading_gate_path": str(live_path)})(),
    )
