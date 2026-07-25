"""local auth timestamps as timestamptz

Revision ID: 007
Revises: 006
Create Date: 2026-07-25

Migration 006 created local_users.created_at / local_sessions.created_at as
TIMESTAMP WITHOUT TIME ZONE, but models/local_auth.py has always produced
timezone-aware UTC datetimes (_utcnow() = datetime.now(timezone.utc)).
asyncpg refuses to bind an aware datetime into a naive timestamp column, so
every signup/session write failed under Postgres with "can't subtract
offset-naive and offset-aware datetimes" — SQLite never enforced this, so it
only surfaced once the Docker Compose Postgres backend was exercised.
"""
from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'local_users', 'created_at',
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'local_sessions', 'created_at',
        type_=sa.DateTime(timezone=True),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        'local_sessions', 'created_at',
        type_=sa.DateTime(),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        'local_users', 'created_at',
        type_=sa.DateTime(),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
    )
