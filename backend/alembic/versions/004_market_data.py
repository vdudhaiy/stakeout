"""market_data table — daily OHLCV price archive, replacing the on-disk CSV cache

Revision ID: 004
Revises: 003
Create Date: 2026-07-20

- new market_data table: one row per (symbol, date), upserted by
  services.price_fetcher. Composite primary key gives dedup for free and an
  indexed range query for "last N days" reads.
"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'market_data',
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('open', sa.Float(), nullable=False),
        sa.Column('high', sa.Float(), nullable=False),
        sa.Column('low', sa.Float(), nullable=False),
        sa.Column('close', sa.Float(), nullable=False),
        sa.Column('volume', sa.BigInteger(), nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='yfinance'),
        sa.PrimaryKeyConstraint('symbol', 'date'),
    )


def downgrade() -> None:
    op.drop_table('market_data')
