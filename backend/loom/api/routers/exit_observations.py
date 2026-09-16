"""Dry-run exit decisions, for review (#56).

The exit layer's dry run exists to be read: as a correctness check on the layer, and more
importantly as a **parameter audit**, since no exit parameter in the roster has ever fired in
live trading and so none has ever been tested against reality (see
docs/strategy-and-universe-gap-analysis.md D0).

Read-only. These rows are deliberately separate from `Signal` so a dry run cannot leak into
Approvals, `Book` performance or confidence calibration.
"""

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.api.deps import get_db
from loom.models import Environment, ExitObservation
from loom.models import Strategy as StrategyModel

router = APIRouter(prefix="/exit-observations", tags=["exit-observations"])

# A stop that fires within a few days of entry is usually measuring noise rather than risk. That
# distinction is the single most useful thing in this data, so it is computed here rather than
# left for a reader to infer from dates.
FAST_STOP_DAYS = 5


@router.get("")
def list_exit_observations(
    environment: str = "demo",
    limit: int = 500,
    session: Session = Depends(get_db),
) -> dict:
    rows = (
        session.execute(
            select(ExitObservation)
            .where(ExitObservation.environment == Environment(environment))
            .order_by(ExitObservation.observed_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    names = {
        s.id: s.name for s in session.execute(select(StrategyModel)).scalars().all()
    }

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[names.get(row.strategy_id, "Manual")].append(
            {
                "id": row.id,
                "instrument": row.instrument,
                "exit_reason": row.exit_reason,
                "decision_price": row.decision_price,
                "quantity": row.quantity,
                "entry_date": row.entry_date,
                "hold_days": row.hold_days,
                "fast_stop": row.exit_reason in ("stop loss", "trailing stop")
                and row.hold_days is not None
                and row.hold_days <= FAST_STOP_DAYS,
                "exit_plan": row.exit_plan,
                "observed_at": row.observed_at.isoformat(),
            }
        )

    return {
        "environment": environment,
        "total": len(rows),
        "fast_stop_days": FAST_STOP_DAYS,
        "by_strategy": [
            {
                "strategy": name,
                "count": len(items),
                "fast_stops": sum(1 for i in items if i["fast_stop"]),
                "decisions": items,
            }
            for name, items in sorted(grouped.items())
        ],
    }
