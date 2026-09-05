from loom import killswitch
from loom.models import Environment


def test_engage_and_resume_toggle_the_flag(session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "loom.killswitch.get_settings",
        lambda: type("S", (), {"kill_switch_path": str(tmp_path / "killswitch")})(),
    )

    assert killswitch.is_engaged(Environment.demo) is False

    killswitch.engage(session, Environment.demo)
    assert killswitch.is_engaged(Environment.demo) is True
    assert killswitch.is_engaged(Environment.live) is False  # scoped per-environment

    killswitch.resume(session, Environment.demo)
    assert killswitch.is_engaged(Environment.demo) is False
