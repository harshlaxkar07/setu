"""Database access for the Setu backend.

One Postgres database (ADR-004): relational tables, PostGIS, pgvector, and the
LangGraph checkpointer tables all live here. The connection pool is shared by
the API and the pipeline; the checkpointer manages its own connection.
"""
import os

from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://setu:setu_local_dev@localhost:5432/setu"
)

# Small pool: hackathon-scale, single service (ADR-007 — no queue layer).
pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, open=False)


def setup_checkpointer() -> None:
    """Create the LangGraph checkpointer tables in the shared database.

    Idempotent: langgraph-checkpoint-postgres's setup() only creates missing
    tables. Runs at every backend startup (design D2/D3) so a fresh
    `docker-compose up` always has the checkpointer schema before any run
    can reach the Publish Gate interrupt.
    """
    from langgraph.checkpoint.postgres import PostgresSaver

    # autocommit connection: setup() runs CREATE TABLE IF NOT EXISTS + index DDL.
    with PostgresSaver.from_conn_string(DATABASE_URL) as saver:
        saver.setup()
