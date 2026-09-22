"""The instrument catalogue (ADR-0022).

Syncs Trading 212's own instrument metadata into the `instruments` table and answers questions
about an instrument that nothing in Loom could answer before: what T212 calls it, what currency
it trades in, and whether it is a share or a fund. The last two are what ADR-0019's
`Round-trip cost` needs — FX conversion applies when an instrument's currency differs from the
account's, and UK stamp duty applies to buying a share but not an ETF.

Synced on a schedule rather than fetched per call: this metadata changes rarely, and a
multi-thousand-row response on the path of every order is a different cost profile entirely.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.execution.broker import BrokerClient, BrokerInstrument
from loom.models import AssetType, Instrument

logger = logging.getLogger("loom.instruments")


@dataclass(frozen=True)
class SyncResult:
    added: int
    updated: int
    unchanged: int
    conflicts: list[str]

    @property
    def total(self) -> int:
        return self.added + self.updated + self.unchanged


def _asset_type(value: str) -> AssetType:
    try:
        return AssetType(value)
    except ValueError:
        return AssetType.other


def sync_instruments(session: Session, broker: BrokerClient) -> SyncResult:
    """Upsert every instrument the broker offers, keyed on its T212 ticker.

    Keyed on the T212 ticker rather than the Loom one because T212's is the identifier the broker
    itself is authoritative about (ADR-0003) — a Loom ticker is something we derive, and deriving
    it differently after a format change should show up as a conflict rather than silently
    rewriting which instrument a stored position refers to.
    """
    rows = broker.get_instruments()
    existing = {row.t212_ticker: row for row in session.scalars(select(Instrument)).all()}
    by_loom = {row.loom_ticker: row for row in existing.values()}

    added = updated = unchanged = 0
    conflicts: list[str] = []
    now = datetime.utcnow()

    for item in rows:
        current = existing.get(item.t212_ticker)
        if current is None:
            # A different T212 ticker already claiming this Loom ticker means our derivation
            # produced a collision — two listings of the same symbol, say. Storing it would make
            # `from_t212` ambiguous, so the newcomer is reported and skipped rather than
            # overwriting a mapping that positions may already be recorded against.
            clash = by_loom.get(item.loom_ticker)
            if clash is not None:
                conflicts.append(
                    f"{item.t212_ticker} derives Loom ticker {item.loom_ticker!r}, "
                    f"already held by {clash.t212_ticker}"
                )
                continue
            instrument = Instrument(
                loom_ticker=item.loom_ticker,
                t212_ticker=item.t212_ticker,
                name=item.name,
                currency=item.currency,
                exchange=item.exchange,
                asset_type=_asset_type(item.asset_type),
                isin=item.isin,
                min_trade_quantity=item.min_trade_quantity,
                synced_at=now,
            )
            session.add(instrument)
            by_loom[item.loom_ticker] = instrument
            existing[item.t212_ticker] = instrument
            added += 1
            continue

        changes = _apply(current, item)
        current.synced_at = now
        if changes:
            updated += 1
        else:
            unchanged += 1

    session.commit()
    logger.info(
        "instrument sync: %d added, %d updated, %d unchanged, %d conflicts",
        added, updated, unchanged, len(conflicts),
    )
    return SyncResult(added=added, updated=updated, unchanged=unchanged, conflicts=conflicts)


def _apply(row: Instrument, item: BrokerInstrument) -> bool:
    """Copy changed fields onto an existing row; returns whether anything actually changed.

    `loom_ticker` is deliberately included: if T212 changes a ticker's format, the derived Loom
    ticker moves with it, and every stored position under the old name would otherwise be
    orphaned. It is logged at WARNING because it is the one change here with consequences beyond
    this table."""
    changed = False
    if row.loom_ticker != item.loom_ticker:
        logger.warning(
            "instrument %s: Loom ticker changing %s -> %s; positions recorded under the old "
            "ticker will no longer resolve",
            item.t212_ticker, row.loom_ticker, item.loom_ticker,
        )
        row.loom_ticker = item.loom_ticker
        changed = True
    for attr, value in (
        ("name", item.name),
        ("currency", item.currency),
        ("exchange", item.exchange),
        ("asset_type", _asset_type(item.asset_type)),
        ("isin", item.isin),
        ("min_trade_quantity", item.min_trade_quantity),
    ):
        if getattr(row, attr) != value:
            setattr(row, attr, value)
            changed = True
    return changed


def get(session: Session, loom_ticker: str) -> Instrument | None:
    return session.scalar(select(Instrument).where(Instrument.loom_ticker == loom_ticker))


def search(session: Session, query: str, limit: int = 25) -> list[Instrument]:
    """Case-insensitive match on ticker or name, for the manual-trade instrument picker
    (ADR-0022). Exact ticker matches sort first, since someone typing "TSLA" means that one."""
    if not query.strip():
        return []
    pattern = f"%{query.strip()}%"
    rows = session.scalars(
        select(Instrument)
        .where(Instrument.loom_ticker.ilike(pattern) | Instrument.name.ilike(pattern))
        .limit(limit * 2)
    ).all()
    wanted = query.strip().upper()
    return sorted(rows, key=lambda r: (r.loom_ticker.upper() != wanted, r.loom_ticker))[:limit]
