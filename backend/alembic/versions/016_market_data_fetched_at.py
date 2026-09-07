"""market_data.fetched_at

Revision ID: 016
Revises: 015
Create Date: 2026-09-06

Records when each archived bar was actually pulled from upstream, so the UI
can state a real "prices as of" instead of implying that whatever renders is
current. Nullable on purpose: rows written before this column existed have no
truthful value, and backfilling them with the migration's own timestamp would
claim every historical bar was fetched today.
"""
from alembic import op
import sqlalchemy as sa

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'market_data',
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('market_data', 'fetched_at')
