"""company logos cache

Revision ID: 011
Revises: 010
Create Date: 2026-08-12

New company_logos table: a shared (not user-scoped) cache of Finnhub's
company logo URL per symbol, refreshed rarely by services.logo_service —
logos change on the order of years, not days. Mirrors company_peers' shape.
"""
from alembic import op
import sqlalchemy as sa

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'company_logos',
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('logo_url', sa.String(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('symbol'),
    )


def downgrade() -> None:
    op.drop_table('company_logos')
