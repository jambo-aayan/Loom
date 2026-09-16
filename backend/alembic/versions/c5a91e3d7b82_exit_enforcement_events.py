"""exit enforcement events

Revision ID: c5a91e3d7b82
Revises: b3f8d2c15e47
Create Date: 2026-09-16

Per-environment dry-run/enforcing state for the exit layer (#58). Off by default: no row means
observe only.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5a91e3d7b82'
down_revision: Union[str, Sequence[str], None] = 'b3f8d2c15e47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'exit_enforcement_events',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('environment', sa.Enum('demo', 'live', name='environment'), nullable=False),
        sa.Column('enforcing', sa.Boolean(), nullable=False),
        sa.Column('actor', sa.String(), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('exit_enforcement_events')
