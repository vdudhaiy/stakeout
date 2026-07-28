"""dividend tracking

Revision ID: 008
Revises: 007
Create Date: 2026-07-26

- new dividends table: one row per dividend payment on a holding, keyed by
  (holding_id, date). Auto-populated from yfinance on first purchase / an
  explicit sync, or entered by hand — see portfolio_service.py.
"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None

_MONEY = sa.Numeric(20, 8)


def upgrade() -> None:
    op.create_table(
        'dividends',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('holding_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.String(), nullable=False),
        sa.Column('amount_per_share', _MONEY, nullable=False),
        sa.Column('shares_held', sa.Integer(), nullable=False),
        sa.Column('total_amount', _MONEY, nullable=False),
        sa.Column('source', sa.String(), nullable=False, server_default='manual'),
        sa.ForeignKeyConstraint(['holding_id'], ['holdings.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('holding_id', 'date', name='uq_dividends_holding_date'),
    )
    op.create_index(op.f('ix_dividends_holding_id'), 'dividends', ['holding_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_dividends_holding_id'), table_name='dividends')
    op.drop_table('dividends')
