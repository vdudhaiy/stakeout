"""multiple named portfolios per market

Revision ID: 009
Revises: 008
Create Date: 2026-08-06

- new portfolios table: a user has one or more named portfolios per market,
  each an independent FIFO universe (see models/portfolio.Portfolio).
- holdings: + portfolio_id; ticker uniqueness becomes (portfolio_id, ticker)
  so the same stock can be held in two portfolios with separate lot queues.
- every existing holding is moved into a portfolio named 'main', created per
  (user_id, market) that actually has holdings. Users with no holdings in a
  market get theirs lazily on first request (portfolio_admin_service).
- audit_log: + portfolio_id, nullable. NULL marks a pre-migration row; undo
  resolves those against the market's default portfolio, which is exactly
  where this migration puts every pre-existing holding.
- transactions.holding_id gains the index it always should have had — every
  read of a holding's transactions filters on it.
"""
from alembic import op
import sqlalchemy as sa

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'portfolios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False, server_default='local'),
        sa.Column('market', sa.String(), nullable=False, server_default='US'),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('name_key', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'market', 'name_key', name='uq_portfolios_user_market_name'),
    )
    op.create_index(op.f('ix_portfolios_user_id'), 'portfolios', ['user_id'], unique=False)
    op.create_index(op.f('ix_portfolios_market'), 'portfolios', ['market'], unique=False)

    # Nullable for now — backfilled below, then tightened. Setting NOT NULL
    # before the backfill would fail on any deployment that has data.
    op.add_column('holdings', sa.Column('portfolio_id', sa.Integer(), nullable=True))

    op.execute(
        """
        INSERT INTO portfolios (user_id, market, name, name_key, created_at)
        SELECT DISTINCT user_id, market, 'main', 'main',
               to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US+00:00')
        FROM holdings
        """
    )
    # Joins on the same (user_id, market) pair the insert grouped by, so every
    # holding is guaranteed to find its portfolio.
    op.execute(
        """
        UPDATE holdings SET portfolio_id = (
            SELECT p.id FROM portfolios p
            WHERE p.user_id = holdings.user_id
              AND p.market = holdings.market
              AND p.name_key = 'main'
        )
        """
    )

    op.alter_column('holdings', 'portfolio_id', nullable=False)
    op.create_foreign_key(
        'fk_holdings_portfolio_id', 'holdings', 'portfolios', ['portfolio_id'], ['id'],
    )
    op.create_index(op.f('ix_holdings_portfolio_id'), 'holdings', ['portfolio_id'], unique=False)

    op.drop_constraint('uq_holdings_user_ticker', 'holdings', type_='unique')
    op.create_unique_constraint('uq_holdings_portfolio_ticker', 'holdings', ['portfolio_id', 'ticker'])

    op.add_column('audit_log', sa.Column('portfolio_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_audit_log_portfolio_id'), 'audit_log', ['portfolio_id'], unique=False)

    op.create_index(op.f('ix_transactions_holding_id'), 'transactions', ['holding_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_transactions_holding_id'), table_name='transactions')

    op.drop_index(op.f('ix_audit_log_portfolio_id'), table_name='audit_log')
    op.drop_column('audit_log', 'portfolio_id')

    # A user may by now hold the same ticker in two portfolios, which the
    # restored (user_id, ticker) constraint forbids. Collapse those onto the
    # oldest holding's row first so the constraint can be recreated; the
    # duplicate rows' transactions are re-pointed rather than dropped.
    op.execute(
        """
        UPDATE transactions SET holding_id = keep.id
        FROM holdings dup
        JOIN (
            SELECT user_id, ticker, MIN(id) AS id FROM holdings GROUP BY user_id, ticker
        ) keep ON keep.user_id = dup.user_id AND keep.ticker = dup.ticker
        WHERE transactions.holding_id = dup.id AND dup.id <> keep.id
        """
    )
    op.execute(
        """
        DELETE FROM dividends WHERE holding_id IN (
            SELECT h.id FROM holdings h
            WHERE h.id <> (SELECT MIN(h2.id) FROM holdings h2
                           WHERE h2.user_id = h.user_id AND h2.ticker = h.ticker)
        )
        """
    )
    op.execute(
        """
        DELETE FROM holdings h
        WHERE h.id <> (SELECT MIN(h2.id) FROM holdings h2
                       WHERE h2.user_id = h.user_id AND h2.ticker = h.ticker)
        """
    )

    op.drop_constraint('uq_holdings_portfolio_ticker', 'holdings', type_='unique')
    op.create_unique_constraint('uq_holdings_user_ticker', 'holdings', ['user_id', 'ticker'])

    op.drop_index(op.f('ix_holdings_portfolio_id'), table_name='holdings')
    op.drop_constraint('fk_holdings_portfolio_id', 'holdings', type_='foreignkey')
    op.drop_column('holdings', 'portfolio_id')

    op.drop_index(op.f('ix_portfolios_market'), table_name='portfolios')
    op.drop_index(op.f('ix_portfolios_user_id'), table_name='portfolios')
    op.drop_table('portfolios')
