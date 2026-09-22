"""instruments

Revision ID: d7e2f4a91c63
Revises: c5a91e3d7b82
Create Date: 2026-09-22

Trading 212's instrument metadata, synced into a table (ADR-0022). Replaces the hand-written
four-entry LOOM_TO_T212 map, and is the first place Loom stores an instrument's currency and
asset type — which ADR-0019's cost model needs to know whether FX conversion and UK stamp duty
apply to a trade.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd7e2f4a91c63'
down_revision: Union[str, Sequence[str], None] = 'c5a91e3d7b82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'instruments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('owner_id', sa.String(), nullable=True),
        sa.Column('loom_ticker', sa.String(), nullable=False),
        sa.Column('t212_ticker', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.Column('exchange', sa.String(), nullable=True),
        sa.Column('asset_type', sa.Enum('share', 'etf', 'other', name='assettype'), nullable=False),
        sa.Column('isin', sa.String(), nullable=True),
        sa.Column('min_trade_quantity', sa.Float(), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_instruments_loom_ticker', 'instruments', ['loom_ticker'], unique=True)
    op.create_index('ix_instruments_t212_ticker', 'instruments', ['t212_ticker'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_instruments_t212_ticker', table_name='instruments')
    op.drop_index('ix_instruments_loom_ticker', table_name='instruments')
    op.drop_table('instruments')
    sa.Enum(name='assettype').drop(op.get_bind(), checkfirst=True)
