"""RunTrace helpers — every stage records what it received, produced, and took.

The RunTrace is the explainability record (files/05): the literal answer to
"why did this get a high priority score", and the ops-view source.
"""
import json
import time
from contextlib import contextmanager
from typing import Any

import psycopg


def create_run_trace(conn: psycopg.Connection, citizen_request_id: str,
                     thread_id: str | None = None) -> str:
    row = conn.execute(
        """INSERT INTO run_traces (citizen_request_id, thread_id, status)
           VALUES (%s, %s, 'in_progress') RETURNING id""",
        (citizen_request_id, thread_id),
    ).fetchone()
    conn.commit()
    return str(row[0])


def append_stage(conn: psycopg.Connection, trace_id: str, entry: dict) -> None:
    conn.execute(
        "UPDATE run_traces SET stages = stages || %s::jsonb WHERE id = %s",
        (json.dumps([entry]), trace_id),
    )
    conn.commit()


def set_status(conn: psycopg.Connection, trace_id: str, status: str) -> None:
    conn.execute("UPDATE run_traces SET status = %s WHERE id = %s", (status, trace_id))
    conn.commit()


def set_thread_id(conn: psycopg.Connection, trace_id: str, thread_id: str) -> None:
    conn.execute("UPDATE run_traces SET thread_id = %s WHERE id = %s",
                 (thread_id, trace_id))
    conn.commit()


@contextmanager
def traced_stage(conn: psycopg.Connection, trace_id: str, stage: str,
                 input_ref: Any = None):
    """Record one stage execution: duration, output ref, error, extras.

    Usage:
        with traced_stage(conn, trace_id, "Locate", input_ref=sr_id) as entry:
            ... do work ...
            entry["output_ref"] = str(gr_id)
            entry["alternatives"] = [...]      # optional stage-emitted extras
    On exception the entry records the error and re-raises.
    """
    entry: dict = {"stage": stage, "input_ref": str(input_ref) if input_ref else None}
    start = time.monotonic()
    try:
        yield entry
    except Exception as exc:
        entry["error"] = str(exc)
        raise
    finally:
        entry["duration_ms"] = round((time.monotonic() - start) * 1000, 1)
        try:
            append_stage(conn, trace_id, entry)
        except psycopg.Error:
            # The stage may have left the transaction aborted (e.g. a
            # constraint violation) — clear it so the error entry still lands.
            conn.rollback()
            append_stage(conn, trace_id, entry)
