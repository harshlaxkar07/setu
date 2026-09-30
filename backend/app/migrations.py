"""Additive SQL migrations applied at backend startup (enhancements design D1).

`db/schema.sql` runs only on a fresh Postgres volume, so every schema change
after the MVP lives in `db/migrations/NNN_name.sql`. At startup each file not
yet recorded in `schema_migrations` is applied in filename order, in its own
transaction, and recorded. Files must be idempotent (IF NOT EXISTS, guarded
enum additions) so a half-recorded environment can simply re-run them.

An advisory lock serialises concurrent starters (e.g. two workers booting).
"""
import os
from pathlib import Path

import psycopg

from app import db

MIGRATIONS_DIR = Path(
    os.environ.get(
        "MIGRATIONS_DIR",
        Path(__file__).resolve().parent.parent.parent / "db" / "migrations",
    )
)

# Arbitrary constant key for pg_advisory_lock — "setu" in ASCII.
_LOCK_KEY = 0x73657475


def pending(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """Migration files in `directory` not yet recorded as applied."""
    applied = {
        r[0] for r in conn.execute("SELECT name FROM schema_migrations").fetchall()
    }
    return [p for p in sorted(directory.glob("*.sql")) if p.name not in applied]


def apply_all(directory: Path = MIGRATIONS_DIR,
              database_url: str | None = None) -> list[str]:
    """Apply every pending migration; returns the names applied this call."""
    applied_now: list[str] = []
    if not directory.is_dir():
        return applied_now
    with psycopg.connect(database_url or db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   name       text PRIMARY KEY,
                   applied_at timestamptz NOT NULL DEFAULT now()
               )"""
        )
        conn.execute("SELECT pg_advisory_lock(%s)", (_LOCK_KEY,))
        try:
            for path in pending(conn, directory):
                # ALTER TYPE ... ADD VALUE cannot share a transaction with later
                # use of the new value, so each file is its own transaction and
                # files that add enum values keep them to themselves.
                with conn.transaction():
                    conn.execute(path.read_text())
                    conn.execute(
                        "INSERT INTO schema_migrations (name) VALUES (%s)",
                        (path.name,),
                    )
                applied_now.append(path.name)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_LOCK_KEY,))
    return applied_now
