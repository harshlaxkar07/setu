"""Impact measurement (enhancements task 5.3, design D9) on the seeded
resolved Paud sanitation example plus a fresh partial-window case."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest_a import (
    BASE_LAT,
    BASE_LON,
    cleanup_test_rows,
    connect,
    ensure_pool,
    make_cluster,
    reviewer_headers,
    unit_vector,
)


@pytest.fixture(scope="module")
def client():
    ensure_pool()
    return TestClient(app)


def _sanitation_id():
    with connect() as conn:
        return conn.execute(
            "SELECT id::text FROM demand_clusters WHERE category = 'sanitation'").fetchone()[0]


def test_full_window_before_after(client):
    body = client.get(f"/api/clusters/{_sanitation_id()}/impact").json()
    assert body["available"] is True
    assert (body["complaints_before"], body["complaints_after"]) == (40, 5)
    assert body["after_window_partial"] is False
    assert body["change_pct"] == -87.5
    gap = body["gap"]
    # Built at resolution: one drainage facility before, two after.
    assert (gap["facilities_before"], gap["facilities_after"]) == (1, 2)
    assert (gap["gap_before"], gap["gap_after"]) == (6000.0, 3000.0)


def test_impact_never_changes_verification(client):
    cid = _sanitation_id()
    body = client.get(f"/api/clusters/{cid}/impact").json()
    assert body["verification"]["cluster_status"] == "resolved_unverified"
    with connect() as conn:
        (status,) = conn.execute("SELECT status::text FROM demand_clusters WHERE id=%s",
                                 (cid,)).fetchone()
    assert status == "resolved_unverified"  # fewer complaints ≠ verified


def test_recently_resolved_reports_a_partial_window(client):
    with connect() as conn:
        cid = make_cluster(conn, lonlat=(BASE_LON, BASE_LAT),
                           member_embeddings=[unit_vector(3)])
        conn.execute("UPDATE demand_clusters SET status = 'published' WHERE id = %s", (cid,))
        conn.commit()
        try:
            r = client.post(f"/api/clusters/{cid}/resolve", headers=reviewer_headers())
            assert r.status_code == 200
            body = client.get(f"/api/clusters/{cid}/impact").json()
            assert body["after_window_partial"] is True
            assert body["after_window_elapsed_days"] < 1
            assert body["change_pct"] is None  # never a final figure early
            assert body["resolved_by"]  # the signed-in reviewer
        finally:
            cleanup_test_rows(conn)


def test_unresolved_cluster_has_no_impact_yet(client):
    with connect() as conn:
        (cid,) = conn.execute(
            "SELECT id::text FROM demand_clusters WHERE status = 'active' LIMIT 1").fetchone()
    body = client.get(f"/api/clusters/{cid}/impact").json()
    assert body["available"] is False and "resolved" in body["reason"]


def test_unknown_cluster_is_404(client):
    assert client.get("/api/clusters/00000000-0000-0000-0000-000000000000/impact"
                      ).status_code == 404
