"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'holdings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('company_name', sa.String(), nullable=False, server_default=''),
        sa.Column('shares', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sold_shares', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('average_cost', sa.Float(), nullable=False, server_default='0.0'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_holdings_ticker'), 'holdings', ['ticker'], unique=True)

    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('holding_id', sa.Integer(), nullable=False),
        sa.Column('sale', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('date', sa.String(), nullable=False),
        sa.Column('shares', sa.Integer(), nullable=False),
        sa.Column('bought_at', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('sold_at', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('shares_remaining', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['holding_id'], ['holdings.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('transactions')
    op.drop_index(op.f('ix_holdings_ticker'), table_name='holdings')
    op.drop_table('holdings')
