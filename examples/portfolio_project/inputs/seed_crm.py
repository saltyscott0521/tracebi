"""
Seed the reference project's CRM: apply inputs/seed_crm.sql to the Postgres
database the ``crm`` connection names (connections/crm.yaml, so
TRACEBI_CRM_URL from the environment or the project's .env).

    TRACEBI_CRM_URL=postgresql+psycopg://user:password@host:5432/dbname \\
        python inputs/seed_crm.py

Idempotent: it replaces the issuer_ratings table. Any Postgres works (a
laptop's, the docker-compose `db` service, a managed one); the transform then
reads the table through its `-- source: crm.issuer_ratings` line.
"""

from __future__ import annotations

import os

from tracebi.connections import connection_file, load_connection

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def seed() -> int:
    """Apply the seed script through the connection; returns the rows it holds."""
    connector = load_connection(connection_file("crm", ROOT), root=ROOT)
    connector.connect()
    with open(os.path.join(HERE, "seed_crm.sql"), encoding="utf-8") as fh:
        script = fh.read()
    # The driver's own connection (psycopg): several statements in one
    # execute, which SQLAlchemy's text() would refuse.
    raw = connector._engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(script)
        cur.execute("SELECT count(*) FROM issuer_ratings")
        rows = cur.fetchone()[0]
        raw.commit()
    finally:
        raw.close()
        connector._engine.dispose()
    return rows


if __name__ == "__main__":
    print(f"crm: issuer_ratings seeded, {seed()} rows")
