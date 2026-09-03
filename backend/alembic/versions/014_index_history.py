"""index history

Revision ID: 014
Revises: 013
Create Date: 2026-09-02

New index_history / index_history_refresh tables: daily closing levels for
the benchmark indices (^GSPC, ^NSEI, …) that the Performance page plots a
portfolio against, plus the marker recording how far each one is already
fetched.

Kept out of market_data on purpose — that table is the tradeable universe,
and get_symbols() drives the stocks list, industry/sector maps and startup
repair jobs from it, so an index in there would surface everywhere a ticker
is expected. Shared (not user-scoped), same shape as market_data otherwise.
"""
from alembic import op
import sqlalchemy as sa

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'index_history',
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('symbol', 'date'),
    )
    op.create_table(
        'index_history_refresh',
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('covered_from', sa.Date(), nullable=False),
        sa.Column('covered_to', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('symbol'),
    )


def downgrade() -> None:
    op.drop_table('index_history_refresh')
    op.drop_table('index_history')
