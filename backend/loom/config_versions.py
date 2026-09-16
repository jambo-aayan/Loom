"""Strategy config version lifecycle (CONTEXT.md "Strategy config version"; stories 23, 78).
A version starts as a `draft` — backtestable, not yet official — until explicitly promoted,
which assigns its permanent number and makes it the strategy's current config."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from loom.models import ConfigVersionStatus, StrategyConfigVersion


def current_promoted(session: Session, strategy_id: str) -> StrategyConfigVersion | None:
    """The strategy's live config. `promoted_at` breaks ties: data written before #61 was fixed
    can carry several promoted versions sharing a number, and "which config is live" must still
    have one deterministic answer rather than depending on row order."""
    return session.execute(
        select(StrategyConfigVersion)
        .where(
            StrategyConfigVersion.strategy_id == strategy_id,
            StrategyConfigVersion.status == ConfigVersionStatus.promoted,
        )
        .order_by(
            StrategyConfigVersion.version_number.desc(),
            StrategyConfigVersion.promoted_at.desc(),
        )
    ).scalars().first()


def next_version_number(session: Session, strategy_id: str) -> int:
    """The number the strategy's next promotion should get.

    Only *numbered* versions are considered. That filter is the whole fix for #61: the previous
    implementation ordered every version by `version_number` descending, drafts included, and a
    draft's number is NULL. SQLite sorts NULLs last in DESC so it read the real maximum and
    worked; Postgres sorts them first, so it read a NULL, fell back to 0, and numbered every
    promotion after the first as 1 — colliding with the existing v1 and making "which config is
    live" arbitrary. Excluding NULLs makes the answer independent of the dialect's NULL ordering
    rather than accidentally correct on one of them.
    """
    latest = session.execute(
        select(StrategyConfigVersion)
        .where(
            StrategyConfigVersion.strategy_id == strategy_id,
            StrategyConfigVersion.version_number.isnot(None),
        )
        .order_by(StrategyConfigVersion.version_number.desc())
    ).scalars().first()
    return (latest.version_number + 1) if latest is not None else 1


def create_draft(session: Session, strategy_id: str, params: dict, note: str | None = None) -> StrategyConfigVersion:
    draft = StrategyConfigVersion(
        strategy_id=strategy_id,
        version_number=None,
        status=ConfigVersionStatus.draft,
        params=params,
        note=note,
    )
    session.add(draft)
    session.commit()
    return draft


def promote(session: Session, version: StrategyConfigVersion) -> StrategyConfigVersion:
    version.version_number = next_version_number(session, version.strategy_id)
    version.status = ConfigVersionStatus.promoted
    version.promoted_at = datetime.utcnow()
    session.commit()
    return version


def diff_params(old: dict, new: dict) -> dict:
    """Literal parameter differences between two config versions (story 77) — every key that
    changed, with its old and new value, not narrative text."""
    keys = set(old) | set(new)
    diff = {}
    for key in sorted(keys):
        old_value, new_value = old.get(key), new.get(key)
        if old_value != new_value:
            diff[key] = {"old": old_value, "new": new_value}
    return diff


def duplicate_version_numbers(session: Session) -> list[dict]:
    """Strategies carrying more than one promoted version under the same number — the wreckage
    #61 left behind before it was fixed.

    Reports only. Renumbering promoted versions after the fact would rewrite the changelog that
    exists precisely so a parameter change is traceable, and every `Signal` already references
    its config version by id rather than number, so nothing is broken by leaving history alone.
    What a duplicate does break is reading the changelog, which is a human's call to make.
    """
    from loom.models import Strategy as StrategyModel

    rows = session.execute(
        select(
            StrategyConfigVersion.strategy_id,
            StrategyModel.key,
            StrategyConfigVersion.version_number,
            func.count(StrategyConfigVersion.id),
        )
        .join(StrategyModel, StrategyModel.id == StrategyConfigVersion.strategy_id)
        .where(
            StrategyConfigVersion.status == ConfigVersionStatus.promoted,
            StrategyConfigVersion.version_number.isnot(None),
        )
        .group_by(StrategyConfigVersion.strategy_id, StrategyModel.key, StrategyConfigVersion.version_number)
        .having(func.count(StrategyConfigVersion.id) > 1)
        .order_by(StrategyModel.key, StrategyConfigVersion.version_number)
    ).all()

    return [
        {"strategy_id": strategy_id, "strategy_key": key, "version_number": number, "count": count}
        for strategy_id, key, number, count in rows
    ]
