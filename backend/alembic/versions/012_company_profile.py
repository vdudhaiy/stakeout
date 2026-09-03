"""company profile cache

Revision ID: 012
Revises: 011
Create Date: 2026-09-02

New company_profile table: a shared (not user-scoped) cache of a ticker's
display name, sector and industry, all three of which come from one
yfinance `.info` call. Persisted for the same reason as company_peers and
company_logos — these fields effectively never change, but the in-memory
cache that used to hold them is lost on every restart, so the app re-spent
its most rate-limit-prone upstream call to re-learn facts it already knew.
Mirrors company_peers' shape: plain PK on symbol, no FK, no user_id.
"""
from alembic import op
import sqlalchemy as sa

revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'company_profile',
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False, server_default=''),
        sa.Column('sector', sa.String(), nullable=False, server_default=''),
        sa.Column('industry', sa.String(), nullable=False, server_default=''),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('symbol'),
    )


def downgrade() -> None:
    op.drop_table('company_profile')
