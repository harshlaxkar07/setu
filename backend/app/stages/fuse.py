"""Fuse stage (§5, tasks 5.1–5.2): join infrastructure context onto a DemandCluster.

For a given cluster the stage links, from the seeded InfrastructureDataset rows:

  (a) every functioning InfrastructureFacility of the cluster's category within
      ``constants.SERVICE_RADIUS_M`` of the cluster centroid (PostGIS
      ``ST_DWithin`` over geography, i.e. metres),
  (b) the population figure for the cluster's area, and
  (c) the historical investment label for the cluster's area,

where "the cluster's area" is the region profile whose boundary contains the
centroid, falling back to the nearest boundary. It then writes one
``gap_scores`` row: ``gap_value = population / facility_count`` with **zero
complaint-volume input** — changing a cluster's ``member_count`` can never
change its gap (fusion-scoring spec).

Zero-facility sentinel (design D1, precise definition)
------------------------------------------------------
A cluster with 0 functioning facilities in radius still fuses successfully and
must carry the *category's maximum* gap — never a division error. The sentinel:

    gap_value(zero coverage) = ZERO_FACILITY_GAP_FACTOR × max(finite gaps
                               currently stored for the category)
    …or the cluster's own population when the category has no finite gap yet
    (every cluster unserved — all carry their population and normalization
    handles ties via DEGENERATE_NORM).

Because a finite gap is ``population / facility_count ≤ population``, and the
factor is strictly > 1, a zero-coverage cluster always tops the category's gap
ordering. Fuse applies the sentinel against the gaps stored so far;
``score.score_category`` re-resolves it over the *complete* category before
normalizing (and updates the stored row), so the final stored value never
depends on the order clusters were fused in.
"""
import os
from typing import Any

import psycopg
from psycopg.types.json import Json

from app.constants import (
    CATEGORY_HEALTH,
    CATEGORY_ROAD,
    CATEGORY_WATER,
    SERVICE_RADIUS_M,
)

# DemandCluster category → InfrastructureFacility.facility_type. Unknown
# categories fall back to the category string itself (facility registers for
# future categories are expected to use the category name as the type).
CATEGORY_FACILITY_TYPES: dict[str, str] = {
    CATEGORY_WATER: "water_point",
    CATEGORY_HEALTH: "health_facility",      # hospitals, PHCs, clinics
    CATEGORY_ROAD: "road_access_point",      # all-weather road access points
}

# Which facility register scoring counts (enhancements design D6): the
# synthetic seed by default, so an OpenStreetMap import can never silently
# change the worked example. SCORING_DATASET=openstreetmap opts in.
DEFAULT_SCORING_SOURCE = "synthetic"

# SQL predicate on a facility alias `f`; bind scoring_source() to it.
SCORING_FACILITY_FILTER = (
    "f.dataset_id IN (SELECT id FROM infrastructure_datasets WHERE source = %s)"
)


def scoring_source() -> str:
    return (os.environ.get("SCORING_DATASET") or DEFAULT_SCORING_SOURCE).strip().lower()


# Strictly > 1 so a zero-coverage cluster is strictly the most severe gap in
# its category (see module docstring). Presentation-independent: min-max
# normalization maps it to gap_norm = 1.0 regardless of the exact factor.
ZERO_FACILITY_GAP_FACTOR = 2.0


def facility_type_for(category: str) -> str:
    """Facility type consulted for a cluster category."""
    return CATEGORY_FACILITY_TYPES.get(category, category)


def resolve_zero_facility_gap(finite_gaps: list[float], population: int) -> float:
    """The category max-gap sentinel for a zero-coverage cluster (design D1)."""
    if finite_gaps:
        return ZERO_FACILITY_GAP_FACTOR * max(finite_gaps)
    return float(population)


def region_for_cluster(conn: psycopg.Connection, cluster_id: str) -> dict[str, Any]:
    """Region profile for a cluster: containing boundary first, else nearest.

    Raises ``LookupError`` when no region profile exists at all (the seed
    always provides them; fusing before seeding is a programming error).
    """
    row = conn.execute(
        """
        SELECT rp.id, rp.name, rp.population, rp.investment_label, rp.dataset_id,
               ST_Contains(rp.boundary, dc.centroid) AS contains_centroid
        FROM region_profiles rp, demand_clusters dc
        WHERE dc.id = %s
        ORDER BY ST_Contains(rp.boundary, dc.centroid) DESC,
                 ST_Distance(rp.boundary::geography, dc.centroid::geography) ASC
        LIMIT 1
        """,
        (cluster_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"no region_profiles row available for cluster {cluster_id}")
    return {
        "id": str(row[0]),
        "name": row[1],
        "population": row[2],
        "investment_label": row[3],
        "dataset_id": str(row[4]),
        "contains_centroid": bool(row[5]),
    }


def _finite_gaps_in_category(
    conn: psycopg.Connection, category: str, exclude_cluster_id: str
) -> list[float]:
    """Latest stored finite (facility_count > 0) gap per other category cluster."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (gs.demand_cluster_id) gs.gap_value, gs.facility_count
        FROM gap_scores gs
        JOIN demand_clusters dc ON dc.id = gs.demand_cluster_id
        WHERE dc.category = %s AND gs.demand_cluster_id <> %s
        ORDER BY gs.demand_cluster_id, gs.created_at DESC
        """,
        (category, exclude_cluster_id),
    ).fetchall()
    return [float(gap) for gap, fc in rows if fc > 0]


def fuse_cluster(conn: psycopg.Connection, cluster_id: str) -> dict[str, Any]:
    """Fuse one DemandCluster with seeded infrastructure context.

    Writes (replacing any earlier fuse of the same cluster) one ``gap_scores``
    row and returns the fused record. Does not commit — the caller owns the
    transaction (seed script, pipeline runner, tests).
    """
    cluster = conn.execute(
        "SELECT category, centroid, member_count FROM demand_clusters WHERE id = %s",
        (cluster_id,),
    ).fetchone()
    if cluster is None:
        raise LookupError(f"demand_cluster {cluster_id} not found")
    category, centroid, member_count = cluster
    if centroid is None:
        raise ValueError(f"demand_cluster {cluster_id} has no centroid to fuse against")

    ftype = facility_type_for(category)

    # (a) Functioning facilities of the category's type within the service
    # radius of the centroid — geography cast so the radius is in metres.
    facilities = conn.execute(
        f"""
        SELECT f.id, f.dataset_id
        FROM infrastructure_facilities f, demand_clusters dc
        WHERE dc.id = %s
          AND f.facility_type = %s
          AND f.functioning
          AND ST_DWithin(f.geom::geography, dc.centroid::geography, %s)
          AND {SCORING_FACILITY_FILTER}
        """,
        (cluster_id, ftype, SERVICE_RADIUS_M, scoring_source()),
    ).fetchall()
    facility_ids = [str(f[0]) for f in facilities]
    facility_count = len(facility_ids)

    # (b) + (c) population and investment from the matched region profile.
    region = region_for_cluster(conn, cluster_id)
    population = int(region["population"])

    # InfrastructureGapScore — population / facility coverage, NO volume input.
    if facility_count > 0:
        gap_value = population / facility_count
    else:
        gap_value = resolve_zero_facility_gap(
            _finite_gaps_in_category(conn, category, cluster_id), population
        )

    # Traceability: which dataset rows the join drew from (fusion-scoring spec).
    facility_dataset_ids = sorted({str(f[1]) for f in facilities})
    if not facility_dataset_ids:
        # Zero facilities in radius: cite the register(s) that were consulted.
        consulted = conn.execute(
            f"""SELECT DISTINCT f.dataset_id FROM infrastructure_facilities f
                WHERE f.facility_type = %s AND {SCORING_FACILITY_FILTER}""",
            (ftype, scoring_source()),
        ).fetchall()
        facility_dataset_ids = sorted(str(r[0]) for r in consulted)
    citations = [
        {
            "role": "population+investment",
            "dataset_id": region["dataset_id"],
            "region_profile_id": region["id"],
            "region": region["name"],
        }
    ] + [
        {
            "role": "facilities",
            "dataset_id": ds_id,
            "facility_type": ftype,
            "radius_m": SERVICE_RADIUS_M,
        }
        for ds_id in facility_dataset_ids
    ]

    # Replace any earlier fuse of this cluster (idempotent re-runs).
    conn.execute("DELETE FROM gap_scores WHERE demand_cluster_id = %s", (cluster_id,))
    row = conn.execute(
        """
        INSERT INTO gap_scores
            (demand_cluster_id, population, facility_count, gap_value, dataset_citations)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (cluster_id, population, facility_count, gap_value, Json(citations)),
    ).fetchone()

    return {
        "gap_score_id": str(row[0]),
        "cluster_id": str(cluster_id),
        "category": category,
        "member_count": member_count,
        "population": population,
        "facility_count": facility_count,
        "facility_ids": facility_ids,
        "gap_value": float(gap_value),
        "investment_label": region["investment_label"],
        "region": region["name"],
        "dataset_citations": citations,
    }
