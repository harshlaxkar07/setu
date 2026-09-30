"""Investment planner (enhancements task 5.2, design D4) on the seeded data."""
import pytest
from fastapi.testclient import TestClient

from app.constants import CATEGORY_HEALTH, CATEGORY_WATER
from app.main import app
from tests.conftest_a import connect, ensure_pool

VELHE = (18.3036029, 73.5824636)


@pytest.fixture(scope="module")
def client():
    ensure_pool()
    return TestClient(app)


def _state():
    with connect() as conn:
        return (
            conn.execute("SELECT count(*) FROM infrastructure_facilities").fetchone()[0],
            conn.execute("""SELECT count(*), string_agg(status::text, ',' ORDER BY id)
                            FROM recommendations""").fetchone(),
            conn.execute("SELECT count(*) FROM demand_clusters").fetchone()[0],
        )


def test_water_point_at_velhe_covers_it_without_writing(client):
    before = _state()
    out = client.post("/api/planner/whatif", json={
        "category": CATEGORY_WATER, "lat": VELHE[0], "lon": VELHE[1]}).json()
    velhe = next(r for r in out["affected_regions"] if r["region"] == "Velhe")
    assert (velhe["facilities_before"], velhe["facilities_after"]) == (0, 1)
    assert velhe["uncovered_before"] is True
    assert velhe["gap_after"] == 4800 and velhe["gap_before"] > velhe["gap_after"]
    assert out["newly_covered_population"] >= 4800
    assert any("Velhe" in c["summary"] for c in out["affected_clusters"])
    assert "Advisory" in out["advisory"]
    assert _state() == before  # no facility row added


def test_proposal_far_from_everything_covers_nobody(client):
    out = client.post("/api/planner/whatif", json={
        "category": CATEGORY_WATER, "lat": 19.9, "lon": 75.9})
    assert out.status_code == 200
    body = out.json()
    assert body["newly_covered_population"] == 0
    assert body["affected_regions"] == [] and body["affected_clusters"] == []


def test_allocation_orders_sites_by_marginal_coverage(client):
    out = client.post("/api/planner/allocate",
                      json={"category": CATEGORY_HEALTH, "n": 3}).json()
    sites = out["sites"]
    assert 1 <= len(sites) <= 3
    gains = [s["newly_covered_population"] for s in sites]
    assert gains == sorted(gains, reverse=True) and all(g > 0 for g in gains)
    assert sites[-1]["cumulative_population"] == sum(gains) == out["total_newly_covered"]
    served = [r for s in sites for r in s["regions_served"]]
    assert len(served) == len(set(served))  # no region counted twice
    assert "Aundh" not in served            # already covered


def test_planner_calls_leave_published_state_identical(client):
    before = _state()
    for n in (1, 5):
        client.post("/api/planner/allocate", json={"category": CATEGORY_WATER, "n": n})
    client.post("/api/planner/whatif", json={"category": CATEGORY_HEALTH,
                                             "lat": 18.52, "lon": 73.61})
    assert _state() == before


@pytest.mark.parametrize("body", [
    {"category": "mystery", "lat": 18.5, "lon": 73.8},
    {"category": CATEGORY_WATER, "lat": 123, "lon": 73.8},
])
def test_invalid_whatif_is_422(client, body):
    assert client.post("/api/planner/whatif", json=body).status_code == 422
