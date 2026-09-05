"""Strategy config version lifecycle (CONTEXT.md "Strategy config version"; stories 23, 78).
A version starts as a `draft` — backtestable, not yet official — until explicitly promoted,
which assigns its permanent number and makes it the strategy's current config."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.models import ConfigVersionStatus, StrategyConfigVersion


def current_promoted(session: Session, strategy_id: str) -> StrategyConfigVersion | None:
    return session.execute(
        select(StrategyConfigVersion)
        .where(
            StrategyConfigVersion.strategy_id == strategy_id,
            StrategyConfigVersion.status == ConfigVersionStatus.promoted,
        )
        .order_by(StrategyConfigVersion.version_number.desc())
    ).scalars().first()


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
    latest = session.execute(
        select(StrategyConfigVersion)
        .where(StrategyConfigVersion.strategy_id == version.strategy_id)
        .order_by(StrategyConfigVersion.version_number.desc())
    ).scalars().first()
    next_number = (latest.version_number or 0) + 1 if latest else 1
    version.version_number = next_number
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
