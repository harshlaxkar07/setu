"""Migration runner (enhancements task 1.1, design D1).

Uses a throwaway directory of migration files against the real database, with
unique names so the project's recorded migrations are never touched.
"""
import uuid

import psycopg

from app import db, migrations


def _names(conn):
    return {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}


def test_applies_pending_once_in_order(tmp_path):
    tag = uuid.uuid4().hex[:8]
    table = f"test_mig_{tag}"
    (tmp_path / f"900_{tag}_a.sql").write_text(
        f"CREATE TABLE IF NOT EXISTS {table} (n int);")
    (tmp_path / f"901_{tag}_b.sql").write_text(
        f"INSERT INTO {table} VALUES (1);")
    try:
        first = migrations.apply_all(tmp_path)
        second = migrations.apply_all(tmp_path)
        assert first == [f"900_{tag}_a.sql", f"901_{tag}_b.sql"]
        assert second == []  # recorded: never re-applied
        with psycopg.connect(db.DATABASE_URL) as conn:
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
    finally:
        with psycopg.connect(db.DATABASE_URL, autocommit=True) as conn:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.execute("DELETE FROM schema_migrations WHERE name LIKE %s",
                         (f"%{tag}%",))


def test_failed_migration_is_not_recorded(tmp_path):
    tag = uuid.uuid4().hex[:8]
    (tmp_path / f"900_{tag}_bad.sql").write_text("SELECT * FROM no_such_table;")
    try:
        try:
            migrations.apply_all(tmp_path)
            raised = False
        except psycopg.Error:
            raised = True
        assert raised
        with psycopg.connect(db.DATABASE_URL) as conn:
            assert f"900_{tag}_bad.sql" not in _names(conn)
    finally:
        with psycopg.connect(db.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM schema_migrations WHERE name LIKE %s",
                         (f"%{tag}%",))
