"""Dashboard-facing read API + the simulated mark-resolved action (§6/§8 seam).

The Streamlit dashboard consumes ONLY these endpoints via BACKEND_URL — it has
no database credentials (design D6), so everything it renders must come from
here. Key posture:

  - ``GET /api/recommendations?status=published`` derives SOLELY from recorded
    ``approvals`` rows with decision ``approved`` (design D2). A pending item
    is only visible through ``status=pending`` — the awaiting-review surface.
  - ``POST /api/clusters/{id}/resolve`` is the simulated "mark resolved":
    ``published → resolved_unverified``. Resolution is a claim pending
    verification; the §8 verification bolt-on reuses this endpoint.
  - The gate resume endpoint (``POST /api/gate/{thread_id}/resume``) is §7's —
    the dashboard calls it, but it does not live in this router.

Tier thresholds below are PRESENTATION-only labels for the dashboard/map — the
score itself is entirely defined by the locked constants in
``app.constants`` (design D1).
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row

from app import audit, auth, db

router = APIRouter(prefix="/api", tags=["clusters"])

# Presentation tier cut-points on the [0, 1] composite score (label + color are
# always paired on the dashboard — never color-only).
TIER_HIGH_MIN = 0.66
TIER_MEDIUM_MIN = 0.33


def tier_for(score: float | None) -> str | None:
    """Map a composite PriorityScore to its display tier label."""
    if score is None:
        return None
    if score >= TIER_HIGH_MIN:
        return "High"
    if score >= TIER_MEDIUM_MIN:
        return "Medium"
    return "Low"


_CLUSTER_LIST_SQL = """
SELECT dc.id::text, dc.category, dc.member_count, dc.status::text,
       dc.confidence::text, dc.confidence_reason, dc.representative_summary,
       ST_Y(dc.centroid) AS lat, ST_X(dc.centroid) AS lon,
       ps.score, ps.gap_norm, ps.investment_deficit_norm, ps.volume_norm,
       ps.weights,
       gs.population, gs.facility_count, gs.gap_value, gs.dataset_citations,
       tv.excluded, tv.open_request_flags, tc.open_cluster_flags
FROM demand_clusters dc
LEFT JOIN LATERAL (
    SELECT * FROM priority_scores
    WHERE demand_cluster_id = dc.id ORDER BY created_at DESC LIMIT 1
) ps ON true
LEFT JOIN LATERAL (
    SELECT * FROM gap_scores
    WHERE demand_cluster_id = dc.id ORDER BY created_at DESC LIMIT 1
) gs ON true
-- Trust (enhancements D2): members excluded from counted volume, open flags.
LEFT JOIN LATERAL (
    SELECT count(DISTINCT sr.citizen_request_id)
               FILTER (WHERE tf.status IN ('open', 'confirmed')) AS excluded,
           count(tf.id) FILTER (WHERE tf.status = 'open') AS open_request_flags
    FROM cluster_memberships cm
    JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
    JOIN structured_requests sr ON sr.id = gr.structured_request_id
    JOIN trust_flags tf ON tf.citizen_request_id = sr.citizen_request_id
         AND tf.rule IN ('duplicate_burst', 'repeat_source')
    WHERE cm.demand_cluster_id = dc.id
) tv ON true
LEFT JOIN LATERAL (
    SELECT count(*) AS open_cluster_flags FROM trust_flags
    WHERE demand_cluster_id = dc.id AND citizen_request_id IS NULL
      AND status = 'open'
) tc ON true
"""


def _cluster_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Shape one cluster row for the API: score block only when scored."""
    score = float(row["score"]) if row["score"] is not None else None
    payload = {
        "id": row["id"],
        "category": row["category"],
        "member_count": row["member_count"],
        # Total members minus those excluded by open/confirmed trust flags —
        # the volume the PriorityScore actually uses (enhancements D2).
        "counted_volume": row["member_count"] - int(row["excluded"] or 0),
        "trust": {
            "excluded": int(row["excluded"] or 0),
            "open_request_flags": int(row["open_request_flags"] or 0),
            "open_cluster_flags": int(row["open_cluster_flags"] or 0),
        },
        "status": row["status"],
        "confidence": row["confidence"],
        "confidence_reason": row["confidence_reason"],
        "representative_summary": row["representative_summary"],
        "lat": row["lat"],
        "lon": row["lon"],
        "score": score,
        "tier": tier_for(score),
        "components": None,
        "gap": None,
    }
    if score is not None:
        payload["components"] = {
            "gap_norm": float(row["gap_norm"]),
            "investment_deficit_norm": float(row["investment_deficit_norm"]),
            "volume_norm": float(row["volume_norm"]),
            "weights": row["weights"],
        }
    if row["gap_value"] is not None:
        payload["gap"] = {
            "population": row["population"],
            "facility_count": row["facility_count"],
            "gap_value": float(row["gap_value"]),
            "dataset_citations": row["dataset_citations"],
        }
    return payload


@router.get("/clusters")
def list_clusters() -> list[dict[str, Any]]:
    """All DemandClusters with centroid, composition, and score block if scored.

    Ordered by PriorityScore descending (unscored last) — the ranking the
    dashboard shows is the ranking the backend computed.
    """
    with db.pool.connection() as conn:
        rows = conn.cursor(row_factory=dict_row).execute(
            _CLUSTER_LIST_SQL + " ORDER BY ps.score DESC NULLS LAST, dc.created_at"
        ).fetchall()
    return [_cluster_payload(r) for r in rows]


@router.get("/clusters/{cluster_id}")
def get_cluster(cluster_id: str) -> dict[str, Any]:
    """One cluster in full: score breakdown, gap, every PriorityIndicator, and
    a few raw member complaint texts (displayed unmarked, per provenance rules).
    """
    with db.pool.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        row = cur.execute(
            _CLUSTER_LIST_SQL + " WHERE dc.id = %s", (cluster_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="cluster not found")
        payload = _cluster_payload(row)

        payload["indicators"] = [
            {
                "id": r["id"],
                "name": r["name"],
                "value_text": r["value_text"],
                "value_numeric": (
                    float(r["value_numeric"]) if r["value_numeric"] is not None else None
                ),
                "source_citations": r["source_citations"],
            }
            for r in cur.execute(
                """SELECT id::text, name, value_text, value_numeric, source_citations
                   FROM priority_indicators
                   WHERE demand_cluster_id = %s ORDER BY created_at""",
                (cluster_id,),
            ).fetchall()
        ]

        # Raw citizen voices — rendered WITHOUT the AI-drafted marker, in
        # Devanagari where Hindi (policymaker-dashboard provenance scenarios).
        payload["sample_requests"] = [
            {"raw_text": r["raw_text"], "detected_language": r["detected_language"],
             "channel": r["channel"], "households": r["households_represented"]}
            for r in cur.execute(
                """SELECT cr.raw_text, sr.detected_language, cr.channel::text AS channel,
                          cr.households_represented
                   FROM cluster_memberships cm
                   JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
                   JOIN structured_requests sr ON sr.id = gr.structured_request_id
                   JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
                   WHERE cm.demand_cluster_id = %s AND cr.raw_text IS NOT NULL
                   ORDER BY (cr.channel = 'assisted') DESC, cr.submitted_at LIMIT 3""",
                (cluster_id,),
            ).fetchall()
        ]
    return payload


@router.get("/clusters/{cluster_id}/trace")
def get_cluster_trace(cluster_id: str) -> list[dict[str, Any]]:
    """Run traces for every request that joined the cluster (newest first).

    Empty list is a valid answer pre-§7 — the dashboard renders an explicit
    "no runs traced yet" state, never an error.
    """
    with db.pool.connection() as conn:
        rows = conn.cursor(row_factory=dict_row).execute(
            """
            SELECT rt.id::text, rt.thread_id, rt.status::text, rt.stages,
                   rt.created_at, rt.citizen_request_id::text
            FROM run_traces rt
            JOIN structured_requests sr ON sr.citizen_request_id = rt.citizen_request_id
            JOIN geocoded_requests gr ON gr.structured_request_id = sr.id
            JOIN cluster_memberships cm ON cm.geocoded_request_id = gr.id
            WHERE cm.demand_cluster_id = %s
            ORDER BY rt.created_at DESC
            """,
            (cluster_id,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "thread_id": r["thread_id"],
            "status": r["status"],
            "stages": r["stages"],
            "citizen_request_id": r["citizen_request_id"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@router.get("/recommendations")
def list_recommendations(
    status: Literal["published", "pending", "needs_revision"],
) -> list[dict[str, Any]]:
    """Recommendations by gate state.

    ``published`` derives SOLELY from approvals rows with decision 'approved'
    (design D2) — never from the recommendation's own status column, so a
    dashboard refresh before approval can never leak a pending item here.
    ``pending`` lists gate-awaiting drafts (with thread_id) for the
    awaiting-review surface only. ``needs_revision`` lists drafts a reviewer
    sent back with Request-changes — unpublished, visibly awaiting revision
    (policymaker-dashboard spec), never blended with approved items.
    """
    base = """
        SELECT r.id::text, r.demand_cluster_id::text, r.intervention_text,
               r.intervention_type, r.indicator_citations, r.status::text,
               r.thread_id, r.created_at,
               dc.representative_summary AS cluster_summary,
               dc.category AS cluster_category
    """
    with db.pool.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        if status == "published":
            rows = cur.execute(
                base
                + """ , a.reviewer, a.decided_at
                FROM recommendations r
                JOIN LATERAL (
                    SELECT reviewer, decided_at FROM approvals
                    WHERE recommendation_id = r.id AND decision = 'approved'
                    ORDER BY decided_at DESC LIMIT 1
                ) a ON true
                JOIN demand_clusters dc ON dc.id = r.demand_cluster_id
                ORDER BY a.decided_at DESC
                """
            ).fetchall()
        elif status == "pending":
            rows = cur.execute(
                base
                + """
                FROM recommendations r
                JOIN demand_clusters dc ON dc.id = r.demand_cluster_id
                WHERE r.status = 'pending'
                  AND NOT EXISTS (SELECT 1 FROM approvals a
                                  WHERE a.recommendation_id = r.id)
                ORDER BY r.created_at DESC
                """
            ).fetchall()
        else:  # needs_revision: sent back via Request-changes, awaiting revision
            rows = cur.execute(
                base
                + """
                FROM recommendations r
                JOIN demand_clusters dc ON dc.id = r.demand_cluster_id
                WHERE r.status = 'needs_revision'
                ORDER BY r.created_at DESC
                """
            ).fetchall()
    out = []
    for r in rows:
        item = {
            "id": r["id"],
            "demand_cluster_id": r["demand_cluster_id"],
            "cluster_summary": r["cluster_summary"],
            "cluster_category": r["cluster_category"],
            "intervention_text": r["intervention_text"],
            "intervention_type": r["intervention_type"],
            "indicator_citations": r["indicator_citations"],
            "status": r["status"],
            "thread_id": r["thread_id"],
            "created_at": r["created_at"].isoformat(),
        }
        if status == "published":
            item["approval"] = {
                "reviewer": r["reviewer"],
                "decided_at": r["decided_at"].isoformat(),
            }
        out.append(item)
    return out


@router.post("/clusters/{cluster_id}/resolve")
def resolve_cluster(cluster_id: str,
                    reviewer: str = Depends(auth.require_reviewer)) -> dict[str, Any]:
    """Simulated mark-resolved: ``published → resolved_unverified`` only.

    Resolution is a *claim pending verification* (verification spec) — the
    cluster is never marked verified here. 409 on any other current status so
    the dashboard can surface an honest error instead of faking a transition.
    """
    with db.pool.connection() as conn:
        # Atomic check-and-transition: no window for a concurrent status change
        # between check and update (review finding).
        updated = conn.execute(
            """UPDATE demand_clusters SET status = 'resolved_unverified',
                      resolved_at = now(), resolved_by = %s
               WHERE id = %s AND status = 'published' RETURNING id""",
            (reviewer, cluster_id),
        ).fetchone()
        if updated is None:
            current = conn.execute(
                "SELECT status FROM demand_clusters WHERE id = %s", (cluster_id,)
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="cluster not found")
            raise HTTPException(
                status_code=409,
                detail=f"cluster is '{current[0]}' — only a published cluster "
                       "can be marked resolved",
            )
        audit.append(conn, kind="mark_resolved", subject_id=cluster_id,
                     decision="resolved_unverified", reviewer=reviewer)
        conn.commit()
    return {"id": cluster_id, "status": "resolved_unverified"}


@router.get("/clusters/{cluster_id}/impact")
def cluster_impact(cluster_id: str) -> dict[str, Any]:
    """Before/after complaint rate and gap for a resolved cluster (D9)."""
    from app import impact
    with db.pool.connection() as conn:
        out = impact.measure(conn, cluster_id)
    if out is None:
        raise HTTPException(status_code=404, detail="cluster not found")
    return out
