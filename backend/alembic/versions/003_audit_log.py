"""audit log for transaction/holding mutations (undo support)

Revision ID: 003
Revises: 002
Create Date: 2026-07-20

- new audit_log table: append-only record of buy/sell/delete mutations,
  replayed by portfolio_service.undo_last_action() to reverse the most
  recent action.
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('performed_at', sa.String(), nullable=False),
        sa.Column('undone', sa.Boolean(), nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_log_user_id'), 'audit_log', ['user_id'], unique=False)
    op.create_index(op.f('ix_audit_log_ticker'), 'audit_log', ['ticker'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_log_ticker'), table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_user_id'), table_name='audit_log')
    op.drop_table('audit_log')
