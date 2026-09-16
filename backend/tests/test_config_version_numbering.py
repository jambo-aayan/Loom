"""Strategy config version numbering (#61).

The bug: `promote` worked out the next number by ordering *all* of a strategy's versions by
`version_number` descending and reading the first row — drafts included, whose number is NULL.
NULL ordering is dialect-dependent, so this silently differed between the SQLite the suite runs
on and the Postgres production runs on.
"""

import pytest
from sqlalchemy import nullsfirst, nullslast, select

from loom import db
from loom.config_versions import (
    create_draft,
    current_promoted,
    duplicate_version_numbers,
    next_version_number,
    promote,
)
from loom.models import Strategy as StrategyModel
from loom.models import StrategyConfigVersion as Version
from loom.models import StrategyStyle


@pytest.fixture()
def strategy(session):
    row = StrategyModel(key="k", name="Test Strategy", style=StrategyStyle.trading, live_enabled=False)
    session.add(row)
    session.flush()
    return row


def test_consecutive_promotions_are_numbered_consecutively(session, strategy):
    first = promote(session, create_draft(session, strategy.id, {"a": 1}))
    second = promote(session, create_draft(session, strategy.id, {"a": 2}))
    assert [first.version_number, second.version_number] == [1, 2]


def test_promotion_ignores_unpromoted_drafts(session, strategy):
    promote(session, create_draft(session, strategy.id, {"a": 1}))
    create_draft(session, strategy.id, {"a": 99})  # left as a draft, never promoted
    create_draft(session, strategy.id, {"a": 98})

    promoted = promote(session, create_draft(session, strategy.id, {"a": 2}))
    assert promoted.version_number == 2


def test_numbering_is_immune_to_how_the_database_orders_nulls(session, strategy):
    """The hazard, demonstrated directly: the same unfiltered ordering over the same rows gives
    a different answer depending on where the database puts NULLs. SQLite puts them last, so the
    old implementation happened to work here; Postgres puts them first in DESC, so it read a NULL,
    fell back to 0, and numbered every promotion 1.

    `next_version_number` must not care either way.
    """
    promote(session, create_draft(session, strategy.id, {"a": 1}))
    promote(session, create_draft(session, strategy.id, {"a": 2}))
    create_draft(session, strategy.id, {"a": 3})  # a NULL-numbered row is present

    unfiltered = select(Version).where(Version.strategy_id == strategy.id)
    nulls_last = session.execute(unfiltered.order_by(nullslast(Version.version_number.desc()))).scalars().first()
    nulls_first = session.execute(unfiltered.order_by(nullsfirst(Version.version_number.desc()))).scalars().first()

    assert nulls_last.version_number == 2  # what SQLite gives
    assert nulls_first.version_number is None  # what Postgres gives — the bug
    assert next_version_number(session, strategy.id) == 3  # unaffected by either


def test_numbering_starts_at_one_when_only_drafts_exist(session, strategy):
    create_draft(session, strategy.id, {"a": 1})
    assert next_version_number(session, strategy.id) == 1


def test_current_promoted_is_unambiguous_when_duplicate_numbers_exist(session, strategy):
    """Pre-existing data may already carry duplicates from before the fix. Selection must still
    be deterministic — the most recently promoted row wins."""
    older = promote(session, create_draft(session, strategy.id, {"a": "older"}))
    newer = promote(session, create_draft(session, strategy.id, {"a": "newer"}))
    newer.version_number = older.version_number  # force the collision the old code produced
    session.commit()

    assert current_promoted(session, strategy.id).params == {"a": "newer"}


def test_duplicate_version_numbers_are_reported_not_rewritten(session, strategy):
    first = promote(session, create_draft(session, strategy.id, {"a": 1}))
    second = promote(session, create_draft(session, strategy.id, {"a": 2}))
    second.version_number = first.version_number
    session.commit()

    duplicates = duplicate_version_numbers(session)
    assert duplicates == [{"strategy_id": strategy.id, "strategy_key": "k", "version_number": 1, "count": 2}]

    # Reporting must not repair anything — history stays as it is until a human decides.
    assert session.get(Version, second.id).version_number == first.version_number


def test_no_duplicates_reported_for_healthy_data(session, strategy):
    promote(session, create_draft(session, strategy.id, {"a": 1}))
    promote(session, create_draft(session, strategy.id, {"a": 2}))
    assert duplicate_version_numbers(session) == []
