from loom.config_versions import create_draft, current_promoted, diff_params, promote
from loom.models import ConfigVersionStatus, StrategyStyle
from loom.models import Strategy as StrategyModel


def _seed_strategy(session):
    strategy = StrategyModel(key="low_vol_compounder", name="Low-Vol Compounder", style=StrategyStyle.trading)
    session.add(strategy)
    session.commit()
    return strategy


def test_draft_is_not_current_until_promoted(session):
    strategy = _seed_strategy(session)
    draft = create_draft(session, strategy.id, {"volatility_threshold": 0.02})

    assert draft.status == ConfigVersionStatus.draft
    assert draft.version_number is None
    assert current_promoted(session, strategy.id) is None

    promote(session, draft)

    assert draft.status == ConfigVersionStatus.promoted
    assert draft.version_number == 1
    assert current_promoted(session, strategy.id).id == draft.id


def test_promoting_assigns_incrementing_version_numbers(session):
    strategy = _seed_strategy(session)
    first = create_draft(session, strategy.id, {"a": 1})
    promote(session, first)
    second = create_draft(session, strategy.id, {"a": 2})
    promote(session, second)

    assert first.version_number == 1
    assert second.version_number == 2


def test_diff_params_reports_only_changed_keys():
    diff = diff_params({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 5, "d": 9})

    assert diff == {
        "b": {"old": 2, "new": 5},
        "c": {"old": 3, "new": None},
        "d": {"old": None, "new": 9},
    }
