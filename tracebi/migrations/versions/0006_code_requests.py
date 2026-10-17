"""Code publish requests: Python submitted from a laptop, awaiting an admin.

The files live under ``.tracebi/requests/<id>/``; this row says who asked,
why, what was decided and which pipeline runs the approval started.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "tracebi_code_requests" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "tracebi_code_requests",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("requested_by", sa.Text(), nullable=True),
            sa.Column("requested_role", sa.String(10), nullable=True),
            sa.Column("requested_at", sa.Text(), nullable=False),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("files", sa.Text(), nullable=False),
            sa.Column("decided_by", sa.Text(), nullable=True),
            sa.Column("decided_at", sa.Text(), nullable=True),
            sa.Column("decision_note", sa.Text(), nullable=True),
            sa.Column("version", sa.Text(), nullable=True),
            sa.Column("runs", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if "tracebi_code_requests" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("tracebi_code_requests")
