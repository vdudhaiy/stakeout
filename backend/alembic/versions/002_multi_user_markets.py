"""multi-user, markets, and watchlist

Revision ID: 002
Revises: 001
Create Date: 2026-07-13

- holdings: + user_id, + market; ticker uniqueness becomes (user_id, ticker)
- new watchlist table (per-user tracked tickers; archive stays a shared cache)
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('holdings', sa.Column('user_id', sa.String(), nullable=False, server_default='local'))
    op.add_column('holdings', sa.Column('market', sa.String(), nullable=False, server_default='US'))
    op.execute("UPDATE holdings SET market = 'IN' WHERE ticker LIKE '%.NS' OR ticker LIKE '%.BO'")

    op.drop_index(op.f('ix_holdings_ticker'), table_name='holdings')
    op.create_index(op.f('ix_holdings_ticker'), 'holdings', ['ticker'], unique=False)
    op.create_index(op.f('ix_holdings_user_id'), 'holdings', ['user_id'], unique=False)
    op.create_index(op.f('ix_holdings_market'), 'holdings', ['market'], unique=False)
    op.create_unique_constraint('uq_holdings_user_ticker', 'holdings', ['user_id', 'ticker'])

    op.create_table(
        'watchlist',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False, server_default='local'),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('market', sa.String(), nullable=False, server_default='US'),
        sa.Column('company_name', sa.String(), nullable=False, server_default=''),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'ticker', name='uq_watchlist_user_ticker'),
    )
    op.create_index(op.f('ix_watchlist_user_id'), 'watchlist', ['user_id'], unique=False)
    op.create_index(op.f('ix_watchlist_ticker'), 'watchlist', ['ticker'], unique=False)
    op.create_index(op.f('ix_watchlist_market'), 'watchlist', ['market'], unique=False)


def downgrade() -> None:
    op.drop_table('watchlist')
    op.drop_constraint('uq_holdings_user_ticker', 'holdings', type_='unique')
    op.drop_index(op.f('ix_holdings_market'), table_name='holdings')
    op.drop_index(op.f('ix_holdings_user_id'), table_name='holdings')
    op.drop_index(op.f('ix_holdings_ticker'), table_name='holdings')
    op.create_index(op.f('ix_holdings_ticker'), 'holdings', ['ticker'], unique=True)
    op.drop_column('holdings', 'market')
    op.drop_column('holdings', 'user_id')
