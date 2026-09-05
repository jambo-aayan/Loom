"""insight position tier

Revision ID: 9e8304c02da5
Revises: 0fff947702b3
Create Date: 2026-09-05 21:49:37.193049

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e8304c02da5'
down_revision: Union[str, Sequence[str], None] = '0fff947702b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # batch_alter_table: SQLite has no ALTER COLUMN / inline ADD CONSTRAINT, so this rebuilds the
    # table under the hood there while emitting plain ALTER statements on Postgres (Neon).
    with op.batch_alter_table('insights') as batch_op:
        batch_op.add_column(sa.Column('book_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('instrument', sa.String(), nullable=True))
        batch_op.alter_column('signal_id', existing_type=sa.VARCHAR(), nullable=True)
        batch_op.create_foreign_key('fk_insights_book_id_books', 'books', ['book_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('insights') as batch_op:
        batch_op.drop_constraint('fk_insights_book_id_books', type_='foreignkey')
        batch_op.alter_column('signal_id', existing_type=sa.VARCHAR(), nullable=False)
        batch_op.drop_column('instrument')
        batch_op.drop_column('book_id')
