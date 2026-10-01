"""Trust-flag review API (enhancements task 3.3, design D2).

Flags are never deleted. A reviewer marks a flag `cleared` (legitimate — the
request counts toward complaint volume again) or `confirmed` (manipulation —
it stays excluded). The category is re-scored in the same transaction so the
dashboard immediately reflects the decision, and every review is recorded
with the reviewer and time.
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app import audit, auth, db
from app.stages import fuse as fuse_stage
from app.stages import score as score_stage

router = APIRouter(prefix="/api/trust", tags=["trust"])


class FlagReview(BaseModel):
    decision: Literal["clear", "confirm"]
    reviewer: str | None = Field(default=None, max_length=120)  # ignored (D15)


@router.get("/flags")
def list_flags(status: Literal["open", "cleared", "confirmed", "all"] = "open",
               cluster_id: str | None = None) -> list[dict[str, Any]]:
    """Trust flags, newest first, with the flagged request's text for context."""
    where, params = [], []
    if status != "all":
        where.append("tf.status = %s")
        params.append(status)
    if cluster_id:
        where.append("tf.demand_cluster_id = %s")
        params.append(cluster_id)
    sql = f"""
        SELECT tf.id::text, tf.rule, tf.reason, tf.status, tf.reviewer,
               tf.reviewed_at, tf.created_at,
               tf.demand_cluster_id::text AS cluster_id,
               tf.citizen_request_id::text AS request_id,
               cr.raw_text, dc.representative_summary AS cluster_summary
        FROM trust_flags tf
        LEFT JOIN citizen_requests cr ON cr.id = tf.citizen_request_id
        LEFT JOIN demand_clusters dc ON dc.id = tf.demand_cluster_id
        {"WHERE " + " AND ".join(where) if where else ""}
        ORDER BY tf.created_at DESC LIMIT 500"""
    with db.pool.connection() as conn:
        return conn.cursor(row_factory=dict_row).execute(sql, params).fetchall()


def review_flag(conn, flag_id: str, decision: str, reviewer: str) -> dict[str, Any]:
    """Apply one review inside the caller's transaction; returns the flag."""
    flag = conn.execute(
        """SELECT tf.status, tf.rule, tf.demand_cluster_id, dc.category
           FROM trust_flags tf LEFT JOIN demand_clusters dc
             ON dc.id = tf.demand_cluster_id
           WHERE tf.id = %s FOR UPDATE OF tf""",
        (flag_id,),
    ).fetchone()
    if flag is None:
        raise HTTPException(status_code=404, detail="trust flag not found")
    status, rule, cluster_id, category = flag
    if status != "open":
        raise HTTPException(status_code=409,
                            detail=f"flag already reviewed ({status})")
    new_status = "cleared" if decision == "clear" else "confirmed"
    conn.execute(
        """UPDATE trust_flags SET status = %s, reviewer = %s, reviewed_at = now()
           WHERE id = %s""",
        (new_status, reviewer, flag_id),
    )
    audit.append(conn, kind="trust_flag_review", subject_id=flag_id,
                 decision=new_status, reviewer=reviewer,
                 payload={"rule": rule, "cluster_id": str(cluster_id) if cluster_id else None})
    if rule == "cluster_spike" and new_status == "cleared" and cluster_id:
        # The spike was legitimate: restore confidence it had lowered.
        conn.execute(
            """UPDATE demand_clusters SET confidence = 'high', confidence_reason = NULL
               WHERE id = %s AND confidence = 'medium'
                 AND confidence_reason LIKE 'cluster spike:%%'""",
            (cluster_id,),
        )
    if category:
        # Re-score so counted volume reflects the decision immediately.
        for (cid,) in conn.execute(
                "SELECT id FROM demand_clusters WHERE category = %s AND centroid IS NOT NULL",
                (category,)).fetchall():
            fuse_stage.fuse_cluster(conn, cid)
        score_stage.score_category(conn, category)
    return {"id": flag_id, "status": new_status, "reviewer": reviewer}


@router.post("/flags/{flag_id}/review")
def review(flag_id: str, body: FlagReview,
           reviewer: str = Depends(auth.require_reviewer)) -> dict[str, Any]:
    with db.pool.connection() as conn:
        result = review_flag(conn, flag_id, body.decision, reviewer)
        conn.commit()
    return result
