"""local auth tables on Postgres

Revision ID: 006
Revises: 005
Create Date: 2026-07-21

Historically local email/password auth only ever ran against the local
SQLite database (where init_db's create_all made these tables implicitly),
so no migration existed. The Docker Compose setup changes that: it runs
Postgres with no Supabase project configured, which means local auth is
active against a Postgres database whose schema is managed entirely by
Alembic — so these tables now need a real migration.

Harmless on Supabase deployments: the tables are created but the local
auth router is never mounted there, so they stay empty.
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'local_users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_local_users_email'), 'local_users', ['email'], unique=True)

    op.create_table(
        'local_sessions',
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['local_users.id']),
        sa.PrimaryKeyConstraint('token'),
    )
    op.create_index(op.f('ix_local_sessions_user_id'), 'local_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_local_sessions_user_id'), table_name='local_sessions')
    op.drop_table('local_sessions')
    op.drop_index(op.f('ix_local_users_email'), table_name='local_users')
    op.drop_table('local_users')
