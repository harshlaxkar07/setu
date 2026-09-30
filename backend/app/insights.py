"""Equity insights (enhancements design D3): silent regions and the
complaint-count vs PriorityScore ranking comparison.

Computed on read from stored region, facility and cluster data, reusing the
Fuse stage's service radius, facility mapping, scoring-dataset filter and
zero-coverage sentinel — so a region's gap here is defined exactly as a
cluster's gap is during scoring. Nothing here writes, drafts or publishes.
"""
from typing import Any

import psycopg

from app.constants import (
    EQUITY_CATEGORIES,
    SERVICE_RADIUS_M,
    SILENT_GAP_QUANTILE,
    SILENT_MAX_COMPLAINTS,
)
from app.stages.fuse import (
    SCORING_FACILITY_FILTER,
    facility_type_for,
    resolve_zero_facility_gap,
    scoring_source,
)

SIGNAL_LABEL = "data-derived signal — not citizen demand"


def region_gaps(conn: psycopg.Connection, category: str) -> list[dict[str, Any]]:
    """Every region's gap for a category, with the factors behind it."""
    rows = conn.execute(
        f"""
        SELECT rp.id::text, rp.name, rp.population, rp.investment_label::text,
               rp.settlement_type, rp.vulnerability_index, rp.connectivity_index,
               ST_Y(c.pt) AS lat, ST_X(c.pt) AS lon,
               (SELECT count(*) FROM infrastructure_facilities f
                WHERE f.facility_type = %(ftype)s AND f.functioning
                  AND ST_DWithin(f.geom::geography, c.pt::geography, %(radius)s)
                  AND {SCORING_FACILITY_FILTER.replace('%s', '%(source)s')}) AS facilities,
               (SELECT round(min(ST_Distance(f.geom::geography, c.pt::geography)))
                FROM infrastructure_facilities f
                WHERE f.facility_type = %(ftype)s AND f.functioning
                  AND {SCORING_FACILITY_FILTER.replace('%s', '%(source)s')}) AS nearest_m,
               (SELECT COALESCE(sum(dc.member_count), 0) FROM demand_clusters dc
                WHERE dc.category = %(category)s
                  AND ST_Contains(rp.boundary, dc.centroid)) AS complaints
        FROM region_profiles rp,
             LATERAL (SELECT COALESCE(rp.centroid, ST_Centroid(rp.boundary)) AS pt) c
        ORDER BY rp.name
        """,
        {"ftype": facility_type_for(category), "radius": SERVICE_RADIUS_M,
         "source": scoring_source(), "category": category},
    ).fetchall()
    regions = [
        {"region_id": r[0], "name": r[1], "population": r[2], "investment": r[3],
         "settlement_type": r[4],
         "vulnerability_index": float(r[5]) if r[5] is not None else None,
         "connectivity_index": float(r[6]) if r[6] is not None else None,
         "lat": r[7], "lon": r[8], "facilities_in_radius": int(r[9]),
         "nearest_facility_m": float(r[10]) if r[10] is not None else None,
         "complaints": int(r[11])}
        for r in rows
    ]
    finite = [g["population"] / g["facilities_in_radius"]
              for g in regions if g["facilities_in_radius"] > 0]
    for g in regions:
        g["gap"] = (g["population"] / g["facilities_in_radius"]
                    if g["facilities_in_radius"] > 0
                    else resolve_zero_facility_gap(finite, g["population"]))
    return regions


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def silent_regions(conn: psycopg.Connection,
                   categories: tuple[str, ...] = EQUITY_CATEGORIES) -> list[dict[str, Any]]:
    """High-gap, low-complaint regions per category, most severe first."""
    out = []
    for category in categories:
        regions = region_gaps(conn, category)
        threshold = _quantile([g["gap"] for g in regions], SILENT_GAP_QUANTILE)
        for g in regions:
            if g["gap"] >= threshold and g["complaints"] <= SILENT_MAX_COMPLAINTS:
                reasons = [
                    f"{g['population']:,} residents",
                    (f"no functioning {facility_type_for(category).replace('_', ' ')} "
                     f"within {SERVICE_RADIUS_M:,} m" if g["facilities_in_radius"] == 0
                     else f"{g['facilities_in_radius']} facilities within "
                          f"{SERVICE_RADIUS_M:,} m"),
                    f"{g['complaints']} citizen requests",
                ]
                if g["vulnerability_index"] is not None:
                    reasons.append(f"vulnerability index {g['vulnerability_index']:.2f}")
                if g["connectivity_index"] is not None:
                    reasons.append(f"digital connectivity index {g['connectivity_index']:.2f}")
                out.append({**g, "category": category, "gap_threshold": threshold,
                            "label": SIGNAL_LABEL, "factors": reasons})
    out.sort(key=lambda g: (-g["gap"], -(g["vulnerability_index"] or 0)))
    return out


def ranking_comparison(conn: psycopg.Connection, category: str) -> list[dict[str, Any]]:
    """The category's clusters ranked by raw complaint count and by score."""
    rows = conn.execute(
        """SELECT dc.id::text, dc.representative_summary, dc.member_count, ps.score
           FROM demand_clusters dc
           LEFT JOIN LATERAL (SELECT score FROM priority_scores
                              WHERE demand_cluster_id = dc.id
                              ORDER BY created_at DESC LIMIT 1) ps ON true
           WHERE dc.category = %s""",
        (category,),
    ).fetchall()
    clusters = [{"id": r[0], "summary": r[1], "complaints": r[2],
                 "score": float(r[3]) if r[3] is not None else None} for r in rows]
    by_count = sorted(clusters, key=lambda c: (-c["complaints"], c["id"]))
    by_score = sorted(clusters, key=lambda c: (-(c["score"] if c["score"] is not None
                                                  else -1), c["id"]))
    count_rank = {c["id"]: i + 1 for i, c in enumerate(by_count)}
    score_rank = {c["id"]: i + 1 for i, c in enumerate(by_score)}
    return [{**c, "rank_by_complaints": count_rank[c["id"]],
             "rank_by_score": score_rank[c["id"]],
             "rank_change": count_rank[c["id"]] - score_rank[c["id"]]}
            for c in by_score]
