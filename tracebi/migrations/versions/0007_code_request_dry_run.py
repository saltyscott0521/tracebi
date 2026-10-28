"""A code request's dry run and the commit its approval made.

``dry_run`` is the JSON result of running a proposed SQL transform once
against a throwaway copy (:mod:`tracebi.dryrun`); ``commit_sha`` the git
commit an approval made of the files it wrote, and ``commit_note`` why it
made none when it could not.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_COLUMNS = ("dry_run", "commit_sha", "commit_note")


def upgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tracebi_code_requests")}
    for name in _COLUMNS:
        if name not in have:
            op.add_column("tracebi_code_requests", sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tracebi_code_requests")}
    for name in reversed(_COLUMNS):
        if name in have:
            op.drop_column("tracebi_code_requests", name)
