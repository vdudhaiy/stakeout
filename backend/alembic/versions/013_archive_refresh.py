"""archive refresh markers

Revision ID: 013
Revises: 012
Create Date: 2026-09-02

New archive_refresh table: records the last completed trading day a symbol's
price archive was already asked about. Yahoo publishes a session's daily bar
some time after the close, so in that gap every request finds a stale archive
and re-asks. That marker used to live in a process dict, which the free-tier
host discards many times a day — one wasted upstream call per tracked symbol
per restart. Shared (not user-scoped), plain PK on symbol, like market_data.
"""
from alembic import op
import sqlalchemy as sa

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'archive_refresh',
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('attempted_for', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('symbol'),
    )


def downgrade() -> None:
    op.drop_table('archive_refresh')
