"""OpenStreetMap importer (enhancements task 2.5, design D6).

Uses a recorded real Overpass response (tests/data/overpass_health_aundh.json,
15 health facilities around Aundh). Every dataset a test imports is deleted
again, so the seeded state is untouched.
"""
import json
from pathlib import Path

import httpx
import psycopg
import pytest

from app import db, osm_import
from app.constants import CATEGORY_HEALTH
from app.stages import fuse
from app.stages.score import score_category

SAMPLE = json.loads((Path(__file__).parent / "data" /
                     "overpass_health_aundh.json").read_text())
AUNDH_BBOX = (18.54, 73.79, 18.58, 73.83)


@pytest.fixture()
def conn():
    c = psycopg.connect(db.DATABASE_URL)
    before = {r[0] for r in c.execute("SELECT id FROM infrastructure_datasets")}
    yield c
    c.rollback()
    new = [r[0] for r in c.execute("SELECT id FROM infrastructure_datasets")
           if r[0] not in before]
    for ds in new:
        c.execute("DELETE FROM infrastructure_facilities WHERE dataset_id = %s", (ds,))
        c.execute("DELETE FROM infrastructure_datasets WHERE id = %s", (ds,))
    c.commit()
    c.close()


def _scores(c) -> dict:
    return {str(cid): float(s) for cid, s in c.execute(
        """SELECT DISTINCT ON (demand_cluster_id) demand_cluster_id, score
           FROM priority_scores ORDER BY demand_cluster_id, created_at DESC""")}


def test_query_targets_category_tags_and_bbox():
    q = osm_import.build_query(CATEGORY_HEALTH, AUNDH_BBOX)
    assert '"amenity"~"^(hospital|clinic|doctors)$"' in q
    assert "(18.54,73.79,18.58,73.83)" in q


def test_import_creates_labelled_dataset_in_one_transaction(conn):
    result = osm_import.import_category(conn, CATEGORY_HEALTH, AUNDH_BBOX,
                                        transport=lambda q: SAMPLE)
    assert result["facilities"] == 15
    source, name, imported_at = conn.execute(
        "SELECT source, name, imported_at FROM infrastructure_datasets WHERE id = %s",
        (result["dataset_id"],)).fetchone()
    assert source == "openstreetmap" and "OpenStreetMap" in name
    assert imported_at is not None
    names = {r[0] for r in conn.execute(
        """SELECT name FROM infrastructure_facilities
           WHERE dataset_id = %s AND facility_type = 'health_facility'""",
        (result["dataset_id"],))}
    assert "LifeLine Hospital" in names


def test_seeded_scores_unchanged_by_default(conn, monkeypatch):
    """The import is additive: rescoring healthcare with the default scoring
    source gives identical scores (Aundh's 8 synthetic facilities, not 23)."""
    monkeypatch.delenv("SCORING_DATASET", raising=False)
    before = _scores(conn)
    osm_import.import_category(conn, CATEGORY_HEALTH, AUNDH_BBOX,
                               transport=lambda q: SAMPLE)
    clusters = [r[0] for r in conn.execute(
        "SELECT id FROM demand_clusters WHERE category = %s", (CATEGORY_HEALTH,))]
    for cid in clusters:
        fused = fuse.fuse_cluster(conn, cid)
        assert fused["facility_count"] in (0, 8)
    score_category(conn, CATEGORY_HEALTH)
    after = _scores(conn)
    conn.rollback()  # leave the seeded scores exactly as they were
    for cid in clusters:
        assert abs(after[str(cid)] - before[str(cid)]) < 1e-9


def test_opt_in_scores_against_imported_facilities(conn, monkeypatch):
    osm_import.import_category(conn, CATEGORY_HEALTH, AUNDH_BBOX,
                               transport=lambda q: SAMPLE)
    monkeypatch.setenv("SCORING_DATASET", "openstreetmap")
    aundh = conn.execute(
        """SELECT dc.id FROM demand_clusters dc JOIN region_profiles rp
             ON ST_Contains(rp.boundary, dc.centroid)
           WHERE dc.category = %s AND rp.name = 'Aundh'""",
        (CATEGORY_HEALTH,)).fetchone()[0]
    fused = fuse.fuse_cluster(conn, aundh)
    conn.rollback()
    # Only real OSM facilities within 2 km of the Aundh centroid count now.
    assert fused["facility_count"] > 0
    assert fused["facility_count"] != 8


def test_network_failure_leaves_no_partial_dataset(conn):
    before = conn.execute("SELECT count(*) FROM infrastructure_datasets").fetchone()[0]

    def down(q):
        raise httpx.ConnectError("overpass unreachable")

    with pytest.raises(osm_import.ImportFailed):
        osm_import.import_category(conn, CATEGORY_HEALTH, AUNDH_BBOX, transport=down)
    conn.commit()
    after = conn.execute("SELECT count(*) FROM infrastructure_datasets").fetchone()[0]
    assert after == before


def test_empty_result_is_a_failure_not_an_empty_dataset(conn):
    with pytest.raises(osm_import.ImportFailed):
        osm_import.import_category(conn, CATEGORY_HEALTH, AUNDH_BBOX,
                                   transport=lambda q: {"elements": []})


def test_unsupported_category_is_rejected():
    with pytest.raises(ValueError):
        osm_import.build_query("road_infrastructure", AUNDH_BBOX)
