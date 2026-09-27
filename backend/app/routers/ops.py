"""Ops view (§7 task 7.6): every accepted request observable, halted runs
retryable — no run or request is ever unaccounted for or silently dropped.
"""
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from app import db, pipeline

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/runs")
def list_runs(status: str | None = None) -> list[dict]:
    """Every accepted CitizenRequest with its pipeline status.

    LEFT JOIN: a request whose kick-off died before creating a trace still
    appears (status ``unstarted``) — nothing is unaccounted for. The failed
    stage of a needs-retry run is the last stage entry carrying an error.
    """
    q = """
        SELECT cr.id::text AS citizen_request_id,
               cr.channel::text, cr.submitted_at,
               rt.id::text AS trace_id, rt.thread_id,
               COALESCE(rt.status::text, 'unstarted') AS status,
               (SELECT s->>'stage' FROM jsonb_array_elements(rt.stages) s
                 WHERE s->>'error' IS NOT NULL
                 ORDER BY 1 DESC LIMIT 1) AS failed_stage
        FROM citizen_requests cr
        LEFT JOIN run_traces rt ON rt.citizen_request_id = cr.id
    """
    params: tuple = ()
    if status:
        q += " WHERE COALESCE(rt.status::text, 'unstarted') = %s"
        params = (status,)
    q += " ORDER BY cr.submitted_at DESC"
    with db.pool.connection() as conn:
        rows = conn.cursor(row_factory=dict_row).execute(q, params).fetchall()
    for r in rows:
        r["submitted_at"] = r["submitted_at"].isoformat()
    return rows


@router.post("/runs/{trace_id}/retry")
def retry(trace_id: str) -> dict:
    """Resume a needs-retry run from its failed stage (persisted checkpoint —
    completed upstream stages are not re-executed)."""
    ok = pipeline.retry_run(trace_id)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="run is not in needs_retry state, or the retry failed "
                   "again (still visible here; retry again after fixing the cause)",
        )
    return {"trace_id": trace_id, "resumed": True}
