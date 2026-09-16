"""signal status withdrawn

Revision ID: a1c4e7b90f21
Revises: 0d3da41aad73
Create Date: 2026-09-16

Adds the `withdrawn` SignalStatus (#52): an exit Signal whose Position closed by another route
before it was actioned. Distinct from `rejected` and `expired`, which both imply a decision or a
lapsed opportunity.

Postgres stores this column as a native enum type, so the value has to be added to the type
itself; SQLite stores it as VARCHAR and needs nothing.
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a1c4e7b90f21'
down_revision: Union[str, Sequence[str], None] = '0d3da41aad73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE signalstatus ADD VALUE IF NOT EXISTS 'withdrawn'")


def downgrade() -> None:
    # Postgres cannot drop a value from an enum type. Removing it would mean recreating the type
    # and rewriting every row referencing it, which is not worth automating for a value that is
    # additive and harmless if unused.
    pass
