"""Location follow-up: re-locate a request after the citizen names the place
(enhancements design D8).

When Locate could not resolve a request, it proceeded flagged as its own
unscoreable cluster and its run halted before Fuse (never dropped). The chat
asks once for the village, ward or landmark; the answer comes here:

  1. the answer is stored (the original raw mention is never modified);
  2. the Locate fallback chain runs on the answer;
  3. if it resolves: in ONE transaction the geocoded request gets its point,
     leaves its placeholder cluster (deleted if now empty) and is clustered
     normally — member counts on both sides stay exact;
  4. the halted pipeline run is pointed at the new cluster and resumed from
     Fuse, so it is scored and reaches (or joins) the Publish Gate.
"""
from typing import Any

import psycopg

from app import db
from app.stages import cluster as cluster_stage
from app.stages import locate


class NotEligible(Exception):
    """The request does not need (or cannot take) a location answer."""


def _placeholder(conn, citizen_request_id: str):
    return conn.execute(
        """SELECT gr.id::text, cm.demand_cluster_id::text, gr.geom IS NULL
           FROM geocoded_requests gr
           JOIN structured_requests sr ON sr.id = gr.structured_request_id
           LEFT JOIN cluster_memberships cm ON cm.geocoded_request_id = gr.id
           WHERE sr.citizen_request_id = %s""",
        (citizen_request_id,),
    ).fetchone()


def needs_location(conn, citizen_request_id: str) -> bool:
    """True while the request has no location and no answer was given yet."""
    row = _placeholder(conn, citizen_request_id)
    if row is None or not row[2]:
        return False
    answered = conn.execute(
        "SELECT 1 FROM location_followups WHERE citizen_request_id = %s",
        (citizen_request_id,)).fetchone()
    return answered is None


def relocate(citizen_request_id: str, answer: str, *, transport=None) -> dict[str, Any]:
    with db.pool.connection() as conn:
        row = _placeholder(conn, citizen_request_id)
        if row is None or not row[2]:
            raise NotEligible("this request already has a location")
        gr_id, old_cluster, _ = row

        found = locate._fallback_locate(conn, answer, transport or locate._live_transport,
                                        try_geocoder=True)
        if found is None:
            try:
                best, _, _ = locate._assess(locate._geocode(
                    locate.compose_query(answer), transport or locate._live_transport))
                if best is not None:
                    found = (float(best["lon"]), float(best["lat"]),
                             f"located from the citizen's follow-up answer '{answer}'")
            except Exception:
                pass
        conn.execute(
            """INSERT INTO location_followups
                 (citizen_request_id, answer, resolved, resolution_reason)
               VALUES (%s, %s, %s, %s)""",
            (citizen_request_id, answer, found is not None,
             found[2] if found else "follow-up answer could not be located"))
        if found is None:
            conn.commit()
            return {"resolved": False, "cluster_id": old_cluster}

        lon, lat, why = found
        with conn.transaction():
            conn.execute(
                """UPDATE geocoded_requests
                   SET geom = ST_SetSRID(ST_MakePoint(%s, %s), 4326),
                       confidence = 'medium', confidence_reason = %s
                   WHERE id = %s""",
                (lon, lat, f"from follow-up answer '{answer}': {why}", gr_id))
            if old_cluster:
                conn.execute("DELETE FROM cluster_memberships WHERE geocoded_request_id = %s",
                             (gr_id,))
                conn.execute(
                    """UPDATE demand_clusters SET member_count = member_count - 1
                       WHERE id = %s""", (old_cluster,))
            result = cluster_stage.run(conn, gr_id, commit=False)
            if old_cluster and old_cluster != result["cluster_id"]:
                # Drop the placeholder once nothing references it any more.
                conn.execute(
                    """DELETE FROM demand_clusters dc WHERE dc.id = %s
                         AND dc.member_count = 0
                         AND NOT EXISTS (SELECT 1 FROM cluster_memberships
                                         WHERE demand_cluster_id = dc.id)
                         AND NOT EXISTS (SELECT 1 FROM recommendations
                                         WHERE demand_cluster_id = dc.id)
                         AND NOT EXISTS (SELECT 1 FROM gap_scores
                                         WHERE demand_cluster_id = dc.id)
                         AND NOT EXISTS (SELECT 1 FROM trust_flags
                                         WHERE demand_cluster_id = dc.id)""",
                    (old_cluster,))
        conn.commit()
        trace = conn.execute(
            """SELECT id::text, thread_id, status::text FROM run_traces
               WHERE citizen_request_id = %s ORDER BY created_at DESC LIMIT 1""",
            (citizen_request_id,)).fetchone()

    resumed = False
    if trace and trace[1] and trace[2] == "needs_retry":
        from app import pipeline
        config = {"configurable": {"thread_id": trace[1]}}
        pipeline.graph().update_state(config, {"cluster_id": result["cluster_id"],
                                               "geocoded_request_id": gr_id},
                                      as_node="trust")
        resumed = pipeline.retry_run(trace[0])
    return {"resolved": True, "cluster_id": result["cluster_id"],
            "reason": why, "pipeline_resumed": resumed}
