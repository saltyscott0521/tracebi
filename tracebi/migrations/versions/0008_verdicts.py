"""The library's last verdict on each build, so a new process paints at once.

One row per build receipt (``manifest``, its absolute path): the verdict a
re-run of its recorded queries gave (:func:`tracebi.desk.verdict`), when it
ran, and ``inputs``, a digest of what it read (:func:`tracebi.desk.verdict_key`;
NULL when an input cannot say whether it changed). A row whose ``inputs``
still match is that verdict; any other row is only what the last re-check
said, shown while the next one runs.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "tracebi_verdicts" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "tracebi_verdicts",
            sa.Column("manifest", sa.String(1024), primary_key=True),
            sa.Column("inputs", sa.String(64), nullable=True),
            sa.Column("verdict", sa.String(32), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("computed_at", sa.Text(), nullable=False),
        )


def downgrade() -> None:
    if "tracebi_verdicts" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("tracebi_verdicts")
