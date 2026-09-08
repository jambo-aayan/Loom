import pytest

from loom import auto_trading_gate


@pytest.fixture(autouse=True)
def _gates_open_by_default(session):
    """Overrides conftest's suite-wide autouse fixture: this file specifically tests the gate's
    genuine default (no event rows at all yet), so it must not get pre-enabled."""
    return


def test_disabled_by_default(session):
    assert auto_trading_gate.is_enabled(session) is False


def test_enable_and_disable_toggle_the_flag(session):
    auto_trading_gate.enable(session)
    assert auto_trading_gate.is_enabled(session) is True

    auto_trading_gate.disable(session)
    assert auto_trading_gate.is_enabled(session) is False
