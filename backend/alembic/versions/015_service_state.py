"""service state key/value store

Revision ID: 015
Revises: 014
Create Date: 2026-09-06

New service_state table: scalar process state that has to outlive the
process. First use is yf_guard's rate-limit cooldown, which until now lived
only in a module global — so a restart (many a day on the free tier, and
triggered by the very page load that then re-hits Yahoo) forgot that we had
just been refused and walked straight back into the throttle. Shared, not
user-scoped, like market_data and archive_refresh.
"""
from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'service_state',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('service_state')
