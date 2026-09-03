"""company peers cache

Revision ID: 010
Revises: 009
Create Date: 2026-08-12

New company_peers table: a shared (not user-scoped) cache of Finnhub's
company-peers list per symbol, refreshed periodically by
services.peers_service. Mirrors market_data's shape — plain PK on symbol,
no FK, no user_id.
"""
from alembic import op
import sqlalchemy as sa

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'company_peers',
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('peers', sa.JSON(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('symbol'),
    )


def downgrade() -> None:
    op.drop_table('company_peers')
