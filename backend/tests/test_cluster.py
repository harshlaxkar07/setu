"""Cluster stage tests (tasks 4.2, 4.3) + the seeded Region A/B assertions.

Embeddings are crafted unit vectors with exact cosine similarities — no
embedding API anywhere. Every created row uses the test- submitter prefix and
is cleaned up per test.
"""
import pytest

from app.constants import (
    CATEGORY_WATER,
    CLUSTER_PROXIMITY_M,
    CLUSTER_SIMILARITY_THRESHOLD,
)
from app.routers import requests as requests_router
from app.stages import cluster
from tests.conftest_a import (
    BASE_LAT,
    BASE_LON,
    cleanup_test_rows,
    connect,
    ensure_pool,
    make_cluster,
    make_request_chain,
    offset_point,
    unit_vector,
    vector_with_cosine,
)

P = (BASE_LON, BASE_LAT)  # test playground, far from the seeded clusters


@pytest.fixture()
def conn():
    c = connect()
    yield c
    c.rollback()  # in case a test left an aborted transaction
    cleanup_test_rows(c)
    c.close()


def member_count(conn, cluster_id) -> int:
    return conn.execute(
        "SELECT member_count FROM demand_clusters WHERE id = %s",
        (cluster_id,)).fetchone()[0]


# --------------------------------------------------------------- membership

def test_similar_nearby_request_joins_existing_cluster(conn):
    cid = make_cluster(conn, lonlat=P,
                       member_embeddings=[vector_with_cosine(0.95)] * 3)
    near = offset_point(*P, east_m=500)
    _, _, gr = make_request_chain(conn, lonlat=near,
                                  embedding=unit_vector(0))

    result = cluster.run(conn, gr)

    assert result["cluster_id"] == cid
    assert result["similarity"] > CLUSTER_SIMILARITY_THRESHOLD
    assert abs(result["similarity"] - 0.95) < 0.01
    assert result["alternatives"] == []
    sim = conn.execute(
        """SELECT similarity_score FROM cluster_memberships
           WHERE geocoded_request_id = %s AND demand_cluster_id = %s""",
        (gr, cid)).fetchone()[0]
    assert abs(float(sim) - result["similarity"]) < 1e-4
    assert member_count(conn, cid) == 4  # bumped


def test_unmatched_far_request_founds_new_cluster(conn):
    cid = make_cluster(conn, lonlat=P,
                       member_embeddings=[vector_with_cosine(0.95)] * 3)
    far = offset_point(*P, east_m=CLUSTER_PROXIMITY_M * 4)  # ~12 km away
    _, _, gr = make_request_chain(conn, lonlat=far, embedding=unit_vector(0),
                                  summary="test new-area water outage")

    result = cluster.run(conn, gr)

    assert result["cluster_id"] != cid
    assert result["similarity"] is None  # founding member
    row = conn.execute(
        """SELECT category, member_count, representative_summary
           FROM demand_clusters WHERE id = %s""",
        (result["cluster_id"],)).fetchone()
    assert row == (CATEGORY_WATER, 1, "test new-area water outage")
    assert member_count(conn, cid) == 3  # untouched


def test_geographically_far_similar_clusters_never_merge(conn):
    """The Region A/B property, mechanically: two same-category clusters far
    apart; a request semantically similar to BOTH joins only the nearby one."""
    near_c = make_cluster(conn, lonlat=P,
                          member_embeddings=[vector_with_cosine(0.9)] * 2)
    far_p = offset_point(*P, north_m=30_000)  # Kothrud↔Velhe-scale distance
    far_c = make_cluster(conn, lonlat=far_p,
                         member_embeddings=[vector_with_cosine(0.9)] * 2)

    _, _, gr = make_request_chain(conn, lonlat=offset_point(*P, east_m=200),
                                  embedding=unit_vector(0))
    result = cluster.run(conn, gr)
    assert result["cluster_id"] == near_c
    assert far_c not in [a["cluster_id"] for a in result["alternatives"]]
    assert member_count(conn, far_c) == 2


def test_same_location_different_category_stays_apart(conn):
    water = make_cluster(conn, lonlat=P,
                         member_embeddings=[vector_with_cosine(0.95)] * 2)
    _, _, gr = make_request_chain(conn, category="road_infrastructure",
                                  lonlat=P, embedding=unit_vector(0))
    result = cluster.run(conn, gr)
    assert result["cluster_id"] != water
    assert member_count(conn, water) == 2


def test_below_similarity_threshold_founds_new_cluster(conn):
    """Nearby and same category, but semantically unrelated → new cluster."""
    cid = make_cluster(conn, lonlat=P,
                       member_embeddings=[unit_vector(5)] * 2)  # orthogonal
    _, _, gr = make_request_chain(conn, lonlat=P, embedding=unit_vector(0))
    result = cluster.run(conn, gr)
    assert result["cluster_id"] != cid


# ---------------------------------------------------------------- ambiguity

def test_ambiguity_joins_higher_similarity_and_returns_alternative(conn):
    c_low = make_cluster(conn, lonlat=offset_point(*P, east_m=400),
                         member_embeddings=[vector_with_cosine(0.84, axis_b=2)] * 2)
    c_high = make_cluster(conn, lonlat=offset_point(*P, east_m=-400),
                          member_embeddings=[vector_with_cosine(0.91, axis_b=1)] * 2)
    _, _, gr = make_request_chain(conn, lonlat=P, embedding=unit_vector(0))

    result = cluster.run(conn, gr)

    assert result["cluster_id"] == c_high
    assert abs(result["similarity"] - 0.91) < 0.01
    assert len(result["alternatives"]) == 1
    alt = result["alternatives"][0]
    assert alt["cluster_id"] == c_low and abs(alt["similarity"] - 0.84) < 0.01
    # exactly ONE membership was created
    assert conn.execute(
        "SELECT count(*) FROM cluster_memberships WHERE geocoded_request_id = %s",
        (gr,)).fetchone()[0] == 1


def test_alternative_is_logged_in_run_trace(conn, monkeypatch):
    """Through the pipeline fallback (task 4.3): the losing candidate and its
    score land in the RunTrace, and the run proceeds without human input."""
    ensure_pool()
    c_low = make_cluster(conn, lonlat=P,
                         member_embeddings=[vector_with_cosine(0.80, axis_b=2)] * 2)
    c_high = make_cluster(conn, lonlat=P,
                          member_embeddings=[vector_with_cosine(0.92, axis_b=1)] * 2)
    cr, sr, gr = make_request_chain(conn, lonlat=P, embedding=unit_vector(0))

    monkeypatch.setattr("app.stages.understand.run",
                        lambda conn_, cid, **kw: sr)
    monkeypatch.setattr("app.stages.locate.run",
                        lambda conn_, sid, **kw: gr)

    requests_router._run_fallback(cr)

    status, stages = conn.execute(
        "SELECT status, stages FROM run_traces WHERE citizen_request_id = %s",
        (cr,)).fetchone()
    assert status == "in_progress"  # proceeded, no halt on ambiguity
    entry = next(s for s in stages if s["stage"] == "Cluster")
    assert entry["output_ref"] == c_high
    assert len(entry["alternatives"]) == 1
    assert entry["alternatives"][0]["cluster_id"] == c_low
    assert abs(entry["alternatives"][0]["similarity"] - 0.80) < 0.01


# --------------------------------------------- degraded requests, never lost

def test_null_geom_flagged_request_founds_flagged_cluster(conn):
    """Documented posture: no geom → new single-member flagged cluster; the
    request proceeds and stays queryable (flag, never drop)."""
    make_cluster(conn, lonlat=P,
                 member_embeddings=[vector_with_cosine(0.95)] * 2)
    _, _, gr = make_request_chain(conn, lonlat=None, embedding=unit_vector(0),
                                  confidence="flagged",
                                  reason="location could not be resolved")
    result = cluster.run(conn, gr)
    conf, reason, count = conn.execute(
        """SELECT confidence, confidence_reason, member_count
           FROM demand_clusters WHERE id = %s""",
        (result["cluster_id"],)).fetchone()
    assert conf == "flagged" and count == 1
    assert "could not be resolved" in reason
    # still part of the stored, queryable demand picture
    assert conn.execute(
        "SELECT 1 FROM cluster_memberships WHERE geocoded_request_id = %s",
        (gr,)).fetchone()


def test_null_embedding_request_founds_new_cluster(conn):
    make_cluster(conn, lonlat=P,
                 member_embeddings=[vector_with_cosine(0.95)] * 2)
    _, _, gr = make_request_chain(conn, lonlat=P, embedding=None)
    result = cluster.run(conn, gr)
    assert member_count(conn, result["cluster_id"]) == 1


# ------------------------------------------------------------- seeded state

def test_seeded_region_a_and_b_are_distinct_clusters(conn):
    """Spec scenario 'Region A and Region B never merge' on the seeded data:
    two water clusters, ~500/~20 members, no cross-membership, and centroids
    far beyond the proximity threshold (so no future merge is possible)."""
    rows = conn.execute(
        """SELECT c.id::text, c.member_count,
                  (SELECT count(*) FROM cluster_memberships m
                   WHERE m.demand_cluster_id = c.id)
           FROM demand_clusters c
           WHERE c.category = %s AND c.representative_summary LIKE %s
           ORDER BY c.member_count DESC""",
        (CATEGORY_WATER, "%Drinking water%")).fetchall()
    assert len(rows) == 2
    (big_id, big_count, big_members), (small_id, small_count, small_members) = rows
    assert big_id != small_id
    assert big_count == big_members == 500
    assert small_count == small_members == 20
    dist = conn.execute(
        """SELECT ST_Distance(a.centroid::geography, b.centroid::geography)
           FROM demand_clusters a, demand_clusters b
           WHERE a.id = %s AND b.id = %s""", (big_id, small_id)).fetchone()[0]
    assert dist > CLUSTER_PROXIMITY_M
