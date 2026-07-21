"""store money as Numeric(20,8) instead of float

Revision ID: 005
Revises: 004
Create Date: 2026-07-20

- holdings.average_cost, transactions.bought_at, transactions.sold_at:
  Float -> Numeric(20, 8). Float accumulates binary rounding error across
  FIFO lot matching (sum of many buy/sell lots); Numeric with Python Decimal
  keeps that arithmetic exact. USING casts the existing float8 values through
  an explicit ::numeric(20,8), which is a lossless representation of any
  value that was already stored in a float column.
"""
from alembic import op
import sqlalchemy as sa

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None

_MONEY = sa.Numeric(20, 8)


def upgrade() -> None:
    op.alter_column('holdings', 'average_cost',
        type_=_MONEY, existing_type=sa.Float(), existing_nullable=False,
        existing_server_default='0.0', server_default='0',
        postgresql_using='average_cost::numeric(20,8)')
    op.alter_column('transactions', 'bought_at',
        type_=_MONEY, existing_type=sa.Float(), existing_nullable=False,
        existing_server_default='0.0', server_default='0',
        postgresql_using='bought_at::numeric(20,8)')
    op.alter_column('transactions', 'sold_at',
        type_=_MONEY, existing_type=sa.Float(), existing_nullable=False,
        existing_server_default='0.0', server_default='0',
        postgresql_using='sold_at::numeric(20,8)')


def downgrade() -> None:
    op.alter_column('transactions', 'sold_at',
        type_=sa.Float(), existing_type=_MONEY, existing_nullable=False,
        existing_server_default='0', server_default='0.0',
        postgresql_using='sold_at::float8')
    op.alter_column('transactions', 'bought_at',
        type_=sa.Float(), existing_type=_MONEY, existing_nullable=False,
        existing_server_default='0', server_default='0.0',
        postgresql_using='bought_at::float8')
    op.alter_column('holdings', 'average_cost',
        type_=sa.Float(), existing_type=_MONEY, existing_nullable=False,
        existing_server_default='0', server_default='0.0',
        postgresql_using='average_cost::float8')
