"""Equity insights (enhancements task 5.1, design D3) on the seeded data."""
import pytest
from fastapi.testclient import TestClient

from app.constants import CATEGORY_HEALTH, CATEGORY_WATER
from app.main import app
from tests.conftest_a import ensure_pool


@pytest.fixture(scope="module")
def client():
    ensure_pool()
    return TestClient(app)


def _silent(client, category):
    return {g["name"]: g for g in
            client.get("/api/insights/silent-regions", params={"category": category}).json()}


def test_zero_request_village_is_silent_with_its_factors(client):
    silent = _silent(client, CATEGORY_HEALTH)
    kurunji = silent["Kurunji"]
    assert kurunji["complaints"] == 0
    assert kurunji["facilities_in_radius"] == 0
    assert kurunji["population"] == 3200
    assert kurunji["label"] == "data-derived signal — not citizen demand"
    assert any("no functioning health facility within 2,000 m" in f
               for f in kurunji["factors"])
    assert any("vulnerability index" in f for f in kurunji["factors"])


def test_well_served_region_is_not_silent(client):
    silent = _silent(client, CATEGORY_HEALTH)
    assert "Aundh" not in silent        # 8 health facilities in radius
    assert "Paud" not in silent         # underserved but reporting (15 requests)


def test_reporting_village_is_not_silent_for_its_category(client):
    assert "Velhe" not in _silent(client, CATEGORY_WATER)  # 20 water requests


def test_silent_regions_never_create_recommendations(client):
    from tests.conftest_a import connect
    with connect() as conn:
        before = conn.execute("SELECT count(*) FROM recommendations").fetchone()[0]
    client.get("/api/insights/silent-regions")
    with connect() as conn:
        assert conn.execute("SELECT count(*) FROM recommendations").fetchone()[0] == before


def test_ranking_comparison_flips_the_worked_example(client):
    rows = client.get("/api/insights/ranking",
                      params={"category": CATEGORY_WATER}).json()
    by_name = {("Kothrud" if "Kothrud" in r["summary"] else "Velhe"): r for r in rows}
    assert by_name["Kothrud"]["rank_by_complaints"] == 1
    assert by_name["Velhe"]["rank_by_score"] == 1
    assert by_name["Velhe"]["rank_change"] == 1     # up one place
    assert by_name["Kothrud"]["rank_change"] == -1  # down one place


def test_unknown_category_is_rejected(client):
    r = client.get("/api/insights/silent-regions", params={"category": "nope"})
    assert r.status_code == 422
