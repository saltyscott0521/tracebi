"""The sign-in groups of a browser session, for folder permissions.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tracebi_sessions")}
    if "groups" not in have:
        op.add_column("tracebi_sessions", sa.Column("groups", sa.Text(), nullable=True))


def downgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tracebi_sessions")}
    if "groups" in have:
        op.drop_column("tracebi_sessions", "groups")
