"""The equity invariant (tasks 5.5–5.6; design D1; fusion-scoring spec).

Runs against the SEEDED demo database (seed.py's task-2.7 Fuse/Score pass):

  1. `test_equity_invariant` — STRICT PriorityScore(Region B / Velhe) >
     PriorityScore(Region A / Kothrud), despite ~25× fewer complaints. This is
     the executable form of governing principle 2: complaint volume never
     overrides the infrastructure gap. The suite FAILS if A ever outranks B.
  2. Formula consistency — the stored score equals the locked formula
     recomputed from the stored components AND from the stored
     PriorityIndicators/gap rows, within 1e-9 (UI rule 1's backend guarantee:
     the breakdown the dashboard shows is exactly the score).

Read-only: nothing here mutates the seeded state.
"""
import os

import psycopg
import pytest

from app.constants import (
    CATEGORY_WATER,
    DEGENERATE_NORM,
    INVESTMENT_DEFICIT,
    WEIGHT_GAP,
    WEIGHT_INVESTMENT_DEFICIT,
    WEIGHT_VOLUME,
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://setu:setu_local_dev@localhost:5434/setu"
)

TOL = 1e-9


@pytest.fixture(scope="module")
def seeded():
    """Seeded water clusters with their latest stored scores, gaps, indicators."""
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """
            SELECT dc.id::text, dc.member_count,
                   ps.score, ps.gap_norm, ps.investment_deficit_norm,
                   ps.volume_norm, ps.weights,
                   gs.gap_value, gs.facility_count, gs.population
            FROM demand_clusters dc
            JOIN LATERAL (
                SELECT * FROM priority_scores
                WHERE demand_cluster_id = dc.id ORDER BY created_at DESC LIMIT 1
            ) ps ON true
            JOIN LATERAL (
                SELECT * FROM gap_scores
                WHERE demand_cluster_id = dc.id ORDER BY created_at DESC LIMIT 1
            ) gs ON true
            WHERE dc.category = %s
            ORDER BY dc.member_count DESC
            """,
            (CATEGORY_WATER,),
        ).fetchall()
        assert len(rows) == 2, (
            "seeded demo database with a scored Region A/B pair required — "
            "run: docker compose exec backend python /app/seed/seed.py"
        )
        indicators = {}
        for r in rows:
            indicators[r[0]] = {
                name: (vt, float(vn) if vn is not None else None)
                for name, vt, vn in conn.execute(
                    """SELECT name, value_text, value_numeric
                       FROM priority_indicators WHERE demand_cluster_id = %s""",
                    (r[0],),
                ).fetchall()
            }

    def unpack(r):
        return {
            "id": r[0], "member_count": r[1], "score": float(r[2]),
            "gap_norm": float(r[3]), "investment_deficit_norm": float(r[4]),
            "volume_norm": float(r[5]), "weights": r[6],
            "gap_value": float(r[7]), "facility_count": r[8],
            "population": r[9], "indicators": indicators[r[0]],
        }

    region_a, region_b = unpack(rows[0]), unpack(rows[1])  # by member_count desc
    assert region_a["member_count"] > region_b["member_count"]
    return region_a, region_b


# --------------------------------------------------------------------------
# Task 5.5 — the invariant itself
# --------------------------------------------------------------------------

def test_equity_invariant(seeded):
    """STRICT: PriorityScore(Region B) > PriorityScore(Region A) on the seed.

    Region A has ~25× the complaint volume; Region B has zero facilities in
    radius and low historical investment. Gap analysis must beat raw counts.
    """
    region_a, region_b = seeded
    assert region_b["score"] > region_a["score"], (
        f"EQUITY INVARIANT VIOLATED: Region A (members="
        f"{region_a['member_count']}, score={region_a['score']}) outranks "
        f"Region B (members={region_b['member_count']}, score={region_b['score']})"
    )


def test_seeded_contrast_shape(seeded):
    """The seeded worked example holds: 0 facilities + max gap on Region B."""
    region_a, region_b = seeded
    assert region_a["facility_count"] == 10
    assert region_b["facility_count"] == 0
    # Zero coverage carries the category's maximum (most severe) gap.
    assert region_b["gap_value"] >= region_a["gap_value"]
    assert region_b["gap_norm"] >= region_a["gap_norm"]


# --------------------------------------------------------------------------
# Task 5.6 — formula consistency: stored score == stored components == formula
# recomputed from the stored PriorityIndicators (no drift, UI rule 1)
# --------------------------------------------------------------------------

def test_stored_score_matches_stored_components(seeded):
    for cluster in seeded:
        expected = (
            WEIGHT_GAP * cluster["gap_norm"]
            + WEIGHT_INVESTMENT_DEFICIT * cluster["investment_deficit_norm"]
            + WEIGHT_VOLUME * cluster["volume_norm"]
        )
        assert abs(cluster["score"] - expected) < TOL
        assert cluster["weights"] == {
            "gap": WEIGHT_GAP,
            "investment_deficit": WEIGHT_INVESTMENT_DEFICIT,
            "volume": WEIGHT_VOLUME,
        }


def _minmax(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi == lo:
        return [DEGENERATE_NORM] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def test_stored_components_match_recomputation_from_indicators(seeded):
    """Normalized components re-derived from the STORED raw evidence — the gap
    rows, the 'historical investment' indicator's deficit value, and the
    'complaint volume' indicator — reproduce the stored norms and score."""
    clusters = list(seeded)

    raw_gap = [c["gap_value"] for c in clusters]
    raw_deficit = [c["indicators"]["historical investment"][1] for c in clusters]
    raw_volume = [c["indicators"]["complaint volume"][1] for c in clusters]
    # The stored deficit is the locked label mapping.
    for c in clusters:
        label = c["indicators"]["historical investment"][0]
        assert c["indicators"]["historical investment"][1] == INVESTMENT_DEFICIT[label]
        assert c["indicators"]["complaint volume"][1] == c["member_count"]

    gap_norm = _minmax(raw_gap)
    deficit_norm = _minmax(raw_deficit)
    volume_norm = _minmax(raw_volume)

    for i, c in enumerate(clusters):
        assert abs(c["gap_norm"] - gap_norm[i]) < TOL
        assert abs(c["investment_deficit_norm"] - deficit_norm[i]) < TOL
        assert abs(c["volume_norm"] - volume_norm[i]) < TOL
        recomputed = (
            WEIGHT_GAP * gap_norm[i]
            + WEIGHT_INVESTMENT_DEFICIT * deficit_norm[i]
            + WEIGHT_VOLUME * volume_norm[i]
        )
        assert abs(c["score"] - recomputed) < TOL
