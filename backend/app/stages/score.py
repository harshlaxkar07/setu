"""Score stage (§5, tasks 5.3–5.4): PriorityIndicators + composite PriorityScore.

For EVERY DemandCluster of a category the stage writes:

  - the four standard ``priority_indicators`` rows — population affected,
    distance to nearest functioning source, historical investment, complaint
    volume — each named, valued, and citing its source rows. Pre-existing
    indicators under other names (e.g. the seeded "possible under-representation
    signal") are kept untouched.
  - one ``priority_scores`` row storing the composite score AND its components
    and weights, so the dashboard breakdown and the formula-consistency test
    read stored data, not recomputation (design D1).

The locked formula (constants are code literals BY CONSTRUCTION — governing
principle 2; volume's 0.2 weight is capped below gap's 0.5):

    PriorityScore = WEIGHT_GAP * gap_norm
                  + WEIGHT_INVESTMENT_DEFICIT * investment_deficit_norm
                  + WEIGHT_VOLUME * volume_norm

Each term is min-max normalized *within the category*. When every cluster in
the category shares the same raw value for an indicator, its normalized value
is the defined constant ``DEGENERATE_NORM`` — never NaN, never an error.

Investment deficit uses ``constants.INVESTMENT_DEFICIT`` (low→1.0, medium→0.5,
high→0.0): lower historical investment ⇒ higher deficit ⇒ higher priority.

Zero-facility gap sentinel: before normalizing, the stage re-resolves the
sentinel for every zero-coverage cluster against the *complete* category (see
``fuse.resolve_zero_facility_gap``) and updates the stored ``gap_scores`` row
when the fuse-time value is stale — the final stored gap never depends on the
order clusters were fused in.
"""
from typing import Any

import psycopg
from psycopg.types.json import Json

from app.constants import (
    DEGENERATE_NORM,
    INVESTMENT_DEFICIT,
    SERVICE_RADIUS_M,
    WEIGHT_GAP,
    WEIGHT_INVESTMENT_DEFICIT,
    WEIGHT_VOLUME,
)
from app.stages import trust as trust_stage
from app.stages.fuse import (
    SCORING_FACILITY_FILTER,
    facility_type_for,
    region_for_cluster,
    resolve_zero_facility_gap,
    scoring_source,
)

# Indicator names this stage owns (re-scoring replaces exactly these rows and
# nothing else — seeded extras like the under-representation signal survive).
INDICATOR_POPULATION = "population affected"
INDICATOR_DISTANCE = "distance to nearest functioning source"
INDICATOR_INVESTMENT = "historical investment"
INDICATOR_VOLUME = "complaint volume"
OWNED_INDICATORS = (
    INDICATOR_POPULATION,
    INDICATOR_DISTANCE,
    INDICATOR_INVESTMENT,
    INDICATOR_VOLUME,
)


def minmax_normalize(raw: dict[str, float]) -> dict[str, float]:
    """Min-max normalize a {cluster_id: value} map within its category cohort.

    All-equal values (including a single-cluster cohort) normalize to the
    defined constant ``DEGENERATE_NORM`` (design D1 degenerate scenario).
    """
    lo, hi = min(raw.values()), max(raw.values())
    if hi == lo:
        return {cid: DEGENERATE_NORM for cid in raw}
    return {cid: (v - lo) / (hi - lo) for cid, v in raw.items()}


def _latest_gap_rows(conn: psycopg.Connection, category: str) -> dict[str, dict]:
    """Latest gap_scores row per cluster of the category, keyed by cluster id."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (gs.demand_cluster_id)
               gs.id, gs.demand_cluster_id, gs.population, gs.facility_count,
               gs.gap_value, gs.dataset_citations
        FROM gap_scores gs
        JOIN demand_clusters dc ON dc.id = gs.demand_cluster_id
        WHERE dc.category = %s
        ORDER BY gs.demand_cluster_id, gs.created_at DESC
        """,
        (category,),
    ).fetchall()
    return {
        str(r[1]): {
            "gap_score_id": str(r[0]),
            "population": int(r[2]),
            "facility_count": int(r[3]),
            "gap_value": float(r[4]),
            "dataset_citations": r[5],
        }
        for r in rows
    }


def _nearest_source_m(
    conn: psycopg.Connection, cluster_id: str, facility_type: str
) -> float | None:
    """Distance (metres) from the centroid to the nearest functioning facility
    of the type, unbounded by the service radius. None when no facility of the
    type exists anywhere in the register."""
    row = conn.execute(
        f"""
        SELECT ST_Distance(f.geom::geography, dc.centroid::geography) AS d
        FROM infrastructure_facilities f, demand_clusters dc
        WHERE dc.id = %s AND f.facility_type = %s AND f.functioning
          AND {SCORING_FACILITY_FILTER}
        ORDER BY d ASC
        LIMIT 1
        """,
        (cluster_id, facility_type, scoring_source()),
    ).fetchone()
    return float(row[0]) if row else None


def _write_indicator(
    conn: psycopg.Connection,
    cluster_id: str,
    name: str,
    value_text: str | None,
    value_numeric: float | None,
    citations: list[dict],
) -> None:
    conn.execute(
        """
        INSERT INTO priority_indicators
            (demand_cluster_id, name, value_text, value_numeric, source_citations)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (cluster_id, name, value_text, value_numeric, Json(citations)),
    )


def score_category(conn: psycopg.Connection, category: str) -> None:
    """Score every DemandCluster of a category (indicators + composite score).

    Requires each cluster to have been fused (a gap_scores row exists) —
    scoring an unfused cluster is a pipeline-ordering error and raises.
    Does not commit; the caller owns the transaction.
    """
    clusters = conn.execute(
        "SELECT id, member_count FROM demand_clusters WHERE category = %s",
        (category,),
    ).fetchall()
    if not clusters:
        return
    member_counts = {str(cid): int(mc) for cid, mc in clusters}

    gaps = _latest_gap_rows(conn, category)
    missing = set(member_counts) - set(gaps)
    if missing:
        raise ValueError(
            f"score_category({category!r}): clusters not yet fused: {sorted(missing)}"
        )

    # --- resolve zero-facility sentinels over the complete category ---------
    finite = [g["gap_value"] for g in gaps.values() if g["facility_count"] > 0]
    for cid, g in gaps.items():
        if g["facility_count"] == 0:
            resolved = resolve_zero_facility_gap(finite, g["population"])
            if resolved != g["gap_value"]:
                conn.execute(
                    "UPDATE gap_scores SET gap_value = %s WHERE id = %s",
                    (resolved, g["gap_score_id"]),
                )
                g["gap_value"] = resolved

    # --- raw indicator values ------------------------------------------------
    regions = {cid: region_for_cluster(conn, cid) for cid in member_counts}
    raw_gap = {cid: gaps[cid]["gap_value"] for cid in member_counts}
    raw_deficit = {
        cid: INVESTMENT_DEFICIT[regions[cid]["investment_label"]]
        for cid in member_counts
    }
    # Complaint volume counts only members not excluded by an open/confirmed
    # trust flag (enhancements D2) — the formula itself is unchanged.
    counted = {cid: trust_stage.counted_volume(conn, cid) for cid in member_counts}
    raw_volume = {cid: float(counted[cid]) for cid in member_counts}

    # --- min-max normalization within the category ---------------------------
    gap_norm = minmax_normalize(raw_gap)
    deficit_norm = minmax_normalize(raw_deficit)
    volume_norm = minmax_normalize(raw_volume)

    weights = {
        "gap": WEIGHT_GAP,
        "investment_deficit": WEIGHT_INVESTMENT_DEFICIT,
        "volume": WEIGHT_VOLUME,
    }
    ftype = facility_type_for(category)

    for cid in member_counts:
        g, region = gaps[cid], regions[cid]

        # Replace exactly the indicators this stage owns (extras preserved).
        conn.execute(
            "DELETE FROM priority_indicators WHERE demand_cluster_id = %s AND name = ANY(%s)",
            (cid, list(OWNED_INDICATORS)),
        )

        region_citation = {
            "dataset_id": region["dataset_id"],
            "region_profile_id": region["id"],
            "region": region["name"],
        }
        _write_indicator(
            conn, cid, INDICATOR_POPULATION,
            f"{g['population']:,} residents in {region['name']}",
            g["population"],
            [region_citation],
        )

        nearest_m = _nearest_source_m(conn, cid, ftype)
        facility_citations = [
            c for c in g["dataset_citations"] if c.get("role") == "facilities"
        ] or [{"role": "facilities", "facility_type": ftype, "note": "register consulted"}]
        if g["facility_count"] == 0:
            prefix = f"no functioning source within the {SERVICE_RADIUS_M:,} m service radius"
            text = (
                f"{prefix}; nearest functioning source ≈ {nearest_m / 1000:.1f} km away"
                if nearest_m is not None
                else f"{prefix}; none in the register"
            )
        else:
            text = (
                f"{nearest_m / 1000:.1f} km to the nearest functioning source "
                f"({g['facility_count']} within the service radius)"
            )
        _write_indicator(
            conn, cid, INDICATOR_DISTANCE, text,
            round(nearest_m, 1) if nearest_m is not None else None,
            facility_citations,
        )

        _write_indicator(
            conn, cid, INDICATOR_INVESTMENT,
            region["investment_label"],
            raw_deficit[cid],  # numeric = mapped deficit (low→1.0 … high→0.0)
            [region_citation],
        )

        excluded = member_counts[cid] - counted[cid]
        volume_text = f"{counted[cid]:,} citizen requests in this cluster"
        if excluded:
            volume_text += (f" ({excluded:,} more excluded as suspected "
                            "manipulation, pending review)")
        _write_indicator(
            conn, cid, INDICATOR_VOLUME,
            volume_text,
            counted[cid],
            [{"source": "demand_cluster", "cluster_id": cid,
              "member_count": member_counts[cid],
              "counted_volume": counted[cid],
              "excluded_by_trust_flags": excluded}],
        )

        # --- composite score: the locked dominance-by-construction formula ---
        score = (
            WEIGHT_GAP * gap_norm[cid]
            + WEIGHT_INVESTMENT_DEFICIT * deficit_norm[cid]
            + WEIGHT_VOLUME * volume_norm[cid]
        )
        conn.execute(
            "DELETE FROM priority_scores WHERE demand_cluster_id = %s", (cid,)
        )
        conn.execute(
            """
            INSERT INTO priority_scores
                (demand_cluster_id, score, gap_norm, investment_deficit_norm,
                 volume_norm, weights)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (cid, score, gap_norm[cid], deficit_norm[cid], volume_norm[cid],
             Json(weights)),
        )


def compute_score(gap_norm: float, investment_deficit_norm: float,
                  volume_norm: float) -> float:
    """The formula alone — used by the formula-consistency test (task 5.6)."""
    return (
        WEIGHT_GAP * gap_norm
        + WEIGHT_INVESTMENT_DEFICIT * investment_deficit_norm
        + WEIGHT_VOLUME * volume_norm
    )
