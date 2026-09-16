"""exit observations

Revision ID: b3f8d2c15e47
Revises: a1c4e7b90f21
Create Date: 2026-09-16

Dry-run decisions from the exit enforcement layer (#53). Its own table rather than a flag on
signals, so a dry run is inert by construction rather than by every counting query remembering
to exclude it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3f8d2c15e47'
down_revision: Union[str, Sequence[str], None] = 'a1c4e7b90f21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'exit_observations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('environment', sa.Enum('demo', 'live', name='environment'), nullable=False),
        sa.Column('book_id', sa.String(), nullable=False),
        sa.Column('strategy_id', sa.String(), nullable=True),
        sa.Column('instrument', sa.String(), nullable=False),
        sa.Column('exit_reason', sa.String(), nullable=False),
        sa.Column('decision_price', sa.Float(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('entry_date', sa.String(), nullable=True),
        sa.Column('hold_days', sa.Integer(), nullable=True),
        sa.Column('exit_plan', sa.JSON(), nullable=False),
        sa.Column('observed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id']),
        sa.ForeignKeyConstraint(['strategy_id'], ['strategies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_exit_observations_environment_observed_at', 'exit_observations',
                    ['environment', 'observed_at'])


def downgrade() -> None:
    op.drop_index('ix_exit_observations_environment_observed_at', table_name='exit_observations')
    op.drop_table('exit_observations')
