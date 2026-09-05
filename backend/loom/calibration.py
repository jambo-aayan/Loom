"""Confidence calibration (story 20, ADR-0009, ticket #36): bucket historical entry-type signals
by strength, use the realized win rate in the bucket a live signal's strength falls into as its
confidence — replacing the hand-tuned placeholder every strategy's `generate_signals` still
computes for `confidence` (kept only as a fallback for when no calibration exists yet, e.g. a
brand-new strategy with no backtest history). Exit-type signals are untouched — they carry no
`strength` and are never looked up here (story 21: high-confidence by construction)."""

from __future__ import annotations

import math
import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.backtest.engine import TradeRecord
from loom.models import ConfidenceCalibration

DEFAULT_NUM_BUCKETS = 4


def compute_buckets(trades: list[TradeRecord], num_buckets: int = DEFAULT_NUM_BUCKETS) -> list[dict]:
    """Buckets *closed* trades with a recorded entry strength into `num_buckets` quantile groups
    (fewer if there aren't enough trades), sorted by strength, each with its realized win rate
    and expectancy — e.g. "RSI 20-25" vs "15-20" in the ADR's own example, generalized to
    whatever continuous strength measure each strategy computes."""
    closed: list[tuple[TradeRecord, float]] = [
        (t, t.entry_strength) for t in trades if t.exit_price is not None and t.entry_strength is not None
    ]
    if not closed:
        return []
    closed.sort(key=lambda pair: pair[1])

    n = len(closed)
    effective_buckets = max(1, min(num_buckets, n))
    chunk_size = math.ceil(n / effective_buckets)

    buckets = []
    for i in range(0, n, chunk_size):
        chunk = [t for t, _strength in closed[i : i + chunk_size]]
        strengths = [strength for _t, strength in closed[i : i + chunk_size]]
        wins = [t for t in chunk if (t.pnl or 0) > 0]
        returns = [t.return_pct for t in chunk if t.return_pct is not None]
        buckets.append(
            {
                "min": min(strengths),
                "max": max(strengths),
                "win_rate": len(wins) / len(chunk),
                "expectancy": statistics.fmean(returns) if returns else 0.0,
                "num_trades": len(chunk),
            }
        )
    return buckets


def lookup_confidence(buckets: list[dict], strength: float) -> float | None:
    """The realized win rate of the bucket `strength` falls into. A strength outside every
    bucket's range (a live signal stronger/weaker than anything seen in the backtest) extrapolates
    to the nearest edge bucket rather than returning nothing."""
    if not buckets:
        return None
    for bucket in buckets:
        if bucket["min"] <= strength <= bucket["max"]:
            return bucket["win_rate"]
    if strength < buckets[0]["min"]:
        return buckets[0]["win_rate"]
    return buckets[-1]["win_rate"]


def save_calibration(
    session: Session,
    strategy_id: str,
    config_version_id: str,
    trades: list[TradeRecord],
    source_backtest_run_id: str | None = None,
    num_buckets: int = DEFAULT_NUM_BUCKETS,
) -> ConfidenceCalibration:
    buckets = compute_buckets(trades, num_buckets)
    existing = session.execute(
        select(ConfidenceCalibration).where(
            ConfidenceCalibration.strategy_id == strategy_id,
            ConfidenceCalibration.config_version_id == config_version_id,
        )
    ).scalar_one_or_none()

    if existing is None:
        existing = ConfidenceCalibration(
            strategy_id=strategy_id, config_version_id=config_version_id, buckets=buckets
        )
        session.add(existing)
    else:
        existing.buckets = buckets

    existing.source_backtest_run_id = source_backtest_run_id
    session.commit()
    return existing


def get_confidence(session: Session, strategy_id: str, config_version_id: str, strength: float) -> float | None:
    """None means no calibration exists yet for this strategy/config version — the caller should
    fall back to the strategy's own placeholder confidence."""
    calibration = session.execute(
        select(ConfidenceCalibration).where(
            ConfidenceCalibration.strategy_id == strategy_id,
            ConfidenceCalibration.config_version_id == config_version_id,
        )
    ).scalar_one_or_none()
    if calibration is None:
        return None
    return lookup_confidence(calibration.buckets, strength)
