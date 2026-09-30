"""Impact measurement (enhancements design D9).

For a resolved cluster: complaint arrivals in the IMPACT_WINDOW_DAYS before
resolution vs the same length after (partial while the after-window is still
open), and the infrastructure gap using facilities that existed at each point.
All figures come from stored timestamps and rows — never estimated by a model.
Impact is reported separately from verification and never changes it.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from app.constants import IMPACT_WINDOW_DAYS, SERVICE_RADIUS_M
from app.stages.fuse import (
    SCORING_FACILITY_FILTER,
    facility_type_for,
    region_for_cluster,
    scoring_source,
)


def _facilities_at(conn, cluster_id: str, ftype: str, when: datetime,
                   *, strictly_before: bool = False) -> int:
    """Facilities in radius that existed at `when` (or strictly before it —
    a facility built at the moment of resolution is part of the "after")."""
    op = "<" if strictly_before else "<="
    (n,) = conn.execute(
        f"""SELECT count(*) FROM infrastructure_facilities f, demand_clusters dc
            WHERE dc.id = %s AND f.facility_type = %s AND f.functioning
              AND f.created_at {op} %s
              AND ST_DWithin(f.geom::geography, dc.centroid::geography, %s)
              AND {SCORING_FACILITY_FILTER}""",
        (cluster_id, ftype, when, SERVICE_RADIUS_M, scoring_source()),
    ).fetchone()
    return int(n)


def measure(conn: psycopg.Connection, cluster_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT category, status::text, resolved_at, resolved_by, centroid IS NOT NULL
           FROM demand_clusters WHERE id = %s""", (cluster_id,)).fetchone()
    if row is None:
        return None
    category, status, resolved_at, resolved_by, has_centroid = row
    verification = conn.execute(
        """SELECT result::text, review_decision FROM verification_records
           WHERE demand_cluster_id = %s ORDER BY created_at DESC LIMIT 1""",
        (cluster_id,)).fetchone()
    base = {"cluster_id": cluster_id, "status": status,
            "verification": {"cluster_status": status,
                             "latest_result": verification[0] if verification else None,
                             "review_decision": verification[1] if verification else None},
            "window_days": IMPACT_WINDOW_DAYS}
    if resolved_at is None:
        return {**base, "available": False,
                "reason": "impact is measured only after the cluster is marked resolved"}

    now = datetime.now(timezone.utc)
    window = timedelta(days=IMPACT_WINDOW_DAYS)
    after_end = min(now, resolved_at + window)
    elapsed_days = max((after_end - resolved_at).total_seconds() / 86400, 0.0)
    (before, after) = conn.execute(
        """SELECT count(*) FILTER (WHERE cm.created_at >= %(s)s AND cm.created_at < %(r)s),
                  count(*) FILTER (WHERE cm.created_at >= %(r)s AND cm.created_at < %(e)s)
           FROM cluster_memberships cm WHERE cm.demand_cluster_id = %(c)s""",
        {"s": resolved_at - window, "r": resolved_at, "e": after_end, "c": cluster_id},
    ).fetchone()
    partial = after_end < resolved_at + window
    change_pct = None
    if before and not partial:
        change_pct = round((after - before) / before * 100, 1)

    gap = None
    if has_centroid:
        ftype = facility_type_for(category)
        population = int(region_for_cluster(conn, cluster_id)["population"])
        f_before = _facilities_at(conn, cluster_id, ftype, resolved_at,
                                  strictly_before=True)
        f_after = _facilities_at(conn, cluster_id, ftype, after_end)
        gap = {"population": population,
               "facilities_before": f_before, "facilities_after": f_after,
               "gap_before": population / f_before if f_before else None,
               "gap_after": population / f_after if f_after else None}
    return {**base, "available": True,
            "resolved_at": resolved_at.isoformat(), "resolved_by": resolved_by,
            "complaints_before": int(before), "complaints_after": int(after),
            "after_window_partial": partial,
            "after_window_elapsed_days": round(elapsed_days, 1),
            "change_pct": change_pct, "gap": gap,
            "note": "Measured from stored timestamps. A drop in complaints does "
                    "not verify the resolution — verification is separate."}
