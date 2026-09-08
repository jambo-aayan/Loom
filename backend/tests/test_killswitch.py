from loom import killswitch
from loom.models import Environment


def test_disabled_by_default(session):
    assert killswitch.is_engaged(session, Environment.demo) is False


def test_engage_and_resume_toggle_the_flag(session):
    assert killswitch.is_engaged(session, Environment.demo) is False

    killswitch.engage(session, Environment.demo)
    assert killswitch.is_engaged(session, Environment.demo) is True
    assert killswitch.is_engaged(session, Environment.live) is False  # scoped per-environment

    killswitch.resume(session, Environment.demo)
    assert killswitch.is_engaged(session, Environment.demo) is False
