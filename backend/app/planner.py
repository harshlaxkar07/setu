"""Investment planner (enhancements design D4) — advisory simulation only.

  whatif    a proposed facility at (lat, lon): which regions and clusters it
            would bring coverage to, their gap before/after, and the
            population newly within the service radius. Nothing is written.
  allocate  up to N sites (from the category's cluster and region centroids)
            chosen greedily to maximise newly covered population — greedy
            maximum coverage is within (1 - 1/e) of optimal.

Coverage and gap use the Fuse stage's definitions (service radius, facility
mapping, scoring dataset), so planner numbers match scored numbers.
"""
from typing import Any

import psycopg

from app.constants import SERVICE_RADIUS_M
from app.insights import region_gaps
from app.stages.fuse import (
    SCORING_FACILITY_FILTER,
    facility_type_for,
    scoring_source,
)

ADVISORY = ("Advisory simulation — no facility, cluster or recommendation is "
            "created; decisions stay with authorised officials.")


def _within(lat1, lon1, lat2, lon2, conn) -> bool:
    (ok,) = conn.execute(
        """SELECT ST_DWithin(ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                             ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, %s)""",
        (lon1, lat1, lon2, lat2, SERVICE_RADIUS_M)).fetchone()
    return bool(ok)


def whatif(conn: psycopg.Connection, category: str, lat: float, lon: float) -> dict[str, Any]:
    regions = region_gaps(conn, category)
    affected, newly_covered = [], 0
    for g in regions:
        if not _within(lat, lon, g["lat"], g["lon"], conn):
            continue
        before, after = g["facilities_in_radius"], g["facilities_in_radius"] + 1
        gained = g["population"] if before == 0 else 0
        newly_covered += gained
        affected.append({
            "region": g["name"], "population": g["population"],
            "facilities_before": before, "facilities_after": after,
            "gap_before": g["gap"], "gap_after": g["population"] / after,
            "uncovered_before": before == 0, "newly_covered_population": gained,
        })

    clusters = []
    for cid, summary, clat, clon, fac in conn.execute(
            f"""SELECT dc.id::text, dc.representative_summary,
                       ST_Y(dc.centroid), ST_X(dc.centroid),
                       (SELECT count(*) FROM infrastructure_facilities f
                        WHERE f.facility_type = %s AND f.functioning
                          AND ST_DWithin(f.geom::geography, dc.centroid::geography, %s)
                          AND {SCORING_FACILITY_FILTER})
                FROM demand_clusters dc
                WHERE dc.category = %s AND dc.centroid IS NOT NULL""",
            (facility_type_for(category), SERVICE_RADIUS_M, scoring_source(),
             category)).fetchall():
        if _within(lat, lon, clat, clon, conn):
            clusters.append({"cluster_id": cid, "summary": summary,
                             "facilities_before": int(fac),
                             "facilities_after": int(fac) + 1})
    return {"category": category, "proposed": {"lat": lat, "lon": lon},
            "service_radius_m": SERVICE_RADIUS_M, "affected_regions": affected,
            "affected_clusters": clusters,
            "newly_covered_population": newly_covered, "advisory": ADVISORY}


def allocate(conn: psycopg.Connection, category: str, n: int) -> dict[str, Any]:
    regions = region_gaps(conn, category)
    uncovered = {g["name"]: g for g in regions if g["facilities_in_radius"] == 0}

    candidates = [{"label": f"{g['name']} (region centre)", "lat": g["lat"], "lon": g["lon"]}
                  for g in regions]
    for summary, clat, clon in conn.execute(
            """SELECT representative_summary, ST_Y(centroid), ST_X(centroid)
               FROM demand_clusters WHERE category = %s AND centroid IS NOT NULL""",
            (category,)).fetchall():
        candidates.append({"label": f"cluster: {summary}", "lat": clat, "lon": clon})

    # Which uncovered regions each candidate would cover.
    reach = []
    for c in candidates:
        covers = {name for name, g in uncovered.items()
                  if _within(c["lat"], c["lon"], g["lat"], g["lon"], conn)}
        reach.append(covers)

    picks, covered, total = [], set(), 0
    for _ in range(max(0, n)):
        best_i, best_gain = None, 0
        for i, covers in enumerate(reach):
            gain = sum(uncovered[r]["population"] for r in covers - covered)
            if gain > best_gain:
                best_i, best_gain = i, gain
        if best_i is None:
            break  # nothing uncovered is reachable any more
        new = sorted(reach[best_i] - covered)
        covered |= set(new)
        total += best_gain
        picks.append({**candidates[best_i], "regions_served": new,
                      "newly_covered_population": best_gain,
                      "cumulative_population": total})
    return {"category": category, "requested": n, "sites": picks,
            "total_newly_covered": total,
            "still_uncovered": sorted(set(uncovered) - covered),
            "advisory": ADVISORY}
