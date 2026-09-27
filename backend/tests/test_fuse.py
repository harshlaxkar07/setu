"""Fuse stage tests (tasks 5.1–5.2) — run inside the backend container:

    docker compose exec -T backend pytest tests/test_fuse.py -q

All write-tests run in a transaction that is rolled back, so the seeded demo
state is never disturbed. No Gemini or Nominatim traffic anywhere here.
"""
import os
import uuid

import psycopg
import pytest

from app.constants import CATEGORY_WATER, SERVICE_RADIUS_M
from app.stages.fuse import (
    ZERO_FACILITY_GAP_FACTOR,
    fuse_cluster,
    resolve_zero_facility_gap,
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://setu:setu_local_dev@localhost:5434/setu"
)


@pytest.fixture()
def conn():
    """One transaction per test, always rolled back — seeded state untouched."""
    with psycopg.connect(DATABASE_URL) as c:
        yield c
        c.rollback()


def _seeded_clusters(conn) -> tuple[str, str]:
    """(region_a_id, region_b_id) — the ~500 / ~20 member seeded water clusters."""
    rows = conn.execute(
        """SELECT id, member_count FROM demand_clusters
           WHERE category = %s ORDER BY member_count DESC""",
        (CATEGORY_WATER,),
    ).fetchall()
    assert len(rows) >= 2, "seeded demo database required (run seed.py first)"
    return str(rows[0][0]), str(rows[-1][0])


def _make_cluster(conn, lat: float, lon: float, member_count: int,
                  category: str = CATEGORY_WATER) -> str:
    row = conn.execute(
        """INSERT INTO demand_clusters
             (category, centroid, representative_summary, member_count)
           VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)
           RETURNING id""",
        (category, lon, lat, f"synthetic test cluster {uuid.uuid4()}", member_count),
    ).fetchone()
    return str(row[0])


def _centroid(conn, cluster_id: str) -> tuple[float, float]:
    row = conn.execute(
        "SELECT ST_Y(centroid), ST_X(centroid) FROM demand_clusters WHERE id = %s",
        (cluster_id,),
    ).fetchone()
    return float(row[0]), float(row[1])


# --------------------------------------------------------------------------
# Requirement: Fuse joins infrastructure context onto a DemandCluster
# --------------------------------------------------------------------------

def test_region_a_fuses_all_ten_facilities_with_citations(conn):
    """Urban cluster links its 10 in-radius facilities, population, investment."""
    region_a, _ = _seeded_clusters(conn)
    fused = fuse_cluster(conn, region_a)

    assert fused["facility_count"] == 10
    assert len(fused["facility_ids"]) == 10
    assert fused["population"] > 0
    assert fused["investment_label"] == "high"
    # Every linked value cites the dataset rows it came from.
    roles = {c["role"] for c in fused["dataset_citations"]}
    assert "population+investment" in roles and "facilities" in roles
    assert all(c.get("dataset_id") for c in fused["dataset_citations"])

    # The gap_scores row landed with the same traceable inputs.
    row = conn.execute(
        """SELECT population, facility_count, gap_value, dataset_citations
           FROM gap_scores WHERE demand_cluster_id = %s
           ORDER BY created_at DESC LIMIT 1""",
        (region_a,),
    ).fetchone()
    assert row is not None
    assert row[1] == 10
    assert float(row[2]) == fused["population"] / 10
    assert len(row[3]) >= 2  # non-empty citations


def test_region_b_zero_facilities_still_fuses(conn):
    """Zero facilities in radius: fusion completes, count 0, sentinel gap."""
    region_a, region_b = _seeded_clusters(conn)
    fused_a = fuse_cluster(conn, region_a)
    fused_b = fuse_cluster(conn, region_b)

    assert fused_b["facility_count"] == 0
    # Sentinel: strictly the category's maximum gap (design D1) — with Region A
    # fused, that is ZERO_FACILITY_GAP_FACTOR × Region A's finite gap.
    assert fused_b["gap_value"] == ZERO_FACILITY_GAP_FACTOR * fused_a["gap_value"]
    assert fused_b["gap_value"] > fused_a["gap_value"]
    # Citations still non-empty: the consulted facility register is cited.
    assert any(c["role"] == "facilities" for c in fused_b["dataset_citations"])


def test_zero_facility_sentinel_without_finite_gaps_uses_population():
    """No finite gap in the category yet → the cluster's own population."""
    assert resolve_zero_facility_gap([], 4800) == 4800.0
    assert resolve_zero_facility_gap([17500.0], 4800) == ZERO_FACILITY_GAP_FACTOR * 17500.0


# --------------------------------------------------------------------------
# Requirement: InfrastructureGapScore is independent of complaint volume
# --------------------------------------------------------------------------

def test_gap_value_ignores_member_count(conn):
    """Equal areas, member counts 500 vs 20 → identical gap (spec scenario)."""
    region_a, _ = _seeded_clusters(conn)
    lat, lon = _centroid(conn, region_a)  # same area ⇒ same facilities/region

    big = _make_cluster(conn, lat, lon, member_count=500)
    small = _make_cluster(conn, lat, lon, member_count=20)
    fused_big = fuse_cluster(conn, big)
    fused_small = fuse_cluster(conn, small)

    assert fused_big["gap_value"] == fused_small["gap_value"]
    assert fused_big["facility_count"] == fused_small["facility_count"]


def test_changing_member_count_leaves_gap_unchanged(conn):
    """Re-fusing after a member_count change reproduces the same gap_value."""
    region_a, _ = _seeded_clusters(conn)
    lat, lon = _centroid(conn, region_a)
    cid = _make_cluster(conn, lat, lon, member_count=20)

    before = fuse_cluster(conn, cid)["gap_value"]
    conn.execute(
        "UPDATE demand_clusters SET member_count = 9999 WHERE id = %s", (cid,)
    )
    after = fuse_cluster(conn, cid)["gap_value"]
    assert before == after  # zero complaint-volume input, by construction


# --------------------------------------------------------------------------
# Join semantics: radius, functioning-only, category type
# --------------------------------------------------------------------------

def test_only_functioning_in_radius_facilities_count(conn):
    """A broken facility and an out-of-radius one never enter the coverage."""
    region_a, _ = _seeded_clusters(conn)
    lat, lon = _centroid(conn, region_a)
    dataset = conn.execute(
        "SELECT id FROM infrastructure_datasets LIMIT 1"
    ).fetchone()[0]

    cid = _make_cluster(conn, lat, lon, member_count=5)
    baseline = fuse_cluster(conn, cid)["facility_count"]

    # Non-functioning point at the centroid: must not count.
    conn.execute(
        """INSERT INTO infrastructure_facilities
             (dataset_id, facility_type, geom, functioning)
           VALUES (%s, 'water_point', ST_SetSRID(ST_MakePoint(%s, %s), 4326), false)""",
        (dataset, lon, lat),
    )
    # Functioning point well outside the service radius (~0.1° ≈ 11 km): no count.
    conn.execute(
        """INSERT INTO infrastructure_facilities
             (dataset_id, facility_type, geom, functioning)
           VALUES (%s, 'water_point', ST_SetSRID(ST_MakePoint(%s, %s), 4326), true)""",
        (dataset, lon + 0.1, lat + 0.1),
    )
    assert fuse_cluster(conn, cid)["facility_count"] == baseline

    # A functioning point just inside the radius DOES count.
    conn.execute(
        """INSERT INTO infrastructure_facilities
             (dataset_id, facility_type, geom, functioning)
           VALUES (%s, 'water_point',
                   ST_SetSRID(ST_MakePoint(%s, %s), 4326), true)""",
        (dataset, lon, lat + (SERVICE_RADIUS_M * 0.5) / 111_320.0),
    )
    assert fuse_cluster(conn, cid)["facility_count"] == baseline + 1


def test_fuse_unknown_cluster_raises(conn):
    with pytest.raises(LookupError):
        fuse_cluster(conn, str(uuid.uuid4()))
