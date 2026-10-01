"""Spam-attack demo (enhancements task 3.4) end to end through the API.

300 near-identical Kothrud complaints go through the real intake API and the
full pipeline (Gemini and the geocoder mocked; embeddings are a real seeded
Kothrud member's vector, so requests truly join the Kothrud cluster).
Afterwards every test row is removed and the seeded state restored.
"""
import importlib.util
import json

import pytest
from fastapi.testclient import TestClient

from app import gemini
from app.main import app
from app.stages import locate as locate_stage
from tests.conftest_a import cleanup_test_state, connect, ensure_pool

spec = importlib.util.spec_from_file_location("spam_attack", "/app/scripts/spam_attack.py")
spam_attack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spam_attack)

UNDERSTAND = json.dumps({"category": "water_infrastructure", "urgency": "high",
                         "summary": "No drinking water in Kothrud for days",
                         "detected_language": "Hindi", "raw_location_mention": "Kothrud"})
RECOMMEND = json.dumps({"intervention_text": "Evaluate tanker scheduling.",
                        "intervention_type": "water_supply_point_evaluation",
                        "cited_indicators": ["population affected"]})


def _water_ranking(conn) -> list[tuple[str, float]]:
    return [(name, float(score)) for name, score in conn.execute(
        """SELECT rp.name, ps.score FROM demand_clusters dc
           JOIN region_profiles rp ON ST_Contains(rp.boundary, dc.centroid)
           JOIN priority_scores ps ON ps.demand_cluster_id = dc.id
           WHERE dc.category = 'water_infrastructure' ORDER BY ps.score DESC""")]


@pytest.fixture()
def kothrud(monkeypatch):
    ensure_pool()
    with connect() as conn:
        (cluster_id, lon, lat, emb) = conn.execute(
            """SELECT dc.id::text, ST_X(dc.centroid), ST_Y(dc.centroid),
                      (SELECT gr.embedding::text FROM cluster_memberships cm
                       JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
                       WHERE cm.demand_cluster_id = dc.id LIMIT 1)
               FROM demand_clusters dc JOIN region_profiles rp
                 ON ST_Contains(rp.boundary, dc.centroid)
               WHERE dc.category = 'water_infrastructure' AND rp.name = 'Kothrud'"""
        ).fetchone()
        confidence = conn.execute(
            "SELECT confidence::text, confidence_reason FROM demand_clusters WHERE id=%s",
            (cluster_id,)).fetchone()
    vec = json.loads(emb)
    monkeypatch.setattr(gemini, "_live_call", lambda p, i=None:
                        RECOMMEND if p.startswith("You are drafting ONE") else UNDERSTAND)
    monkeypatch.setattr(locate_stage, "MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(locate_stage, "_live_transport", lambda q: [{
        "lat": str(lat), "lon": str(lon), "display_name": "Kothrud, Pune",
        "addresstype": "suburb", "importance": 0.6}])
    monkeypatch.setattr(locate_stage, "_live_embedder", lambda t: vec)
    yield cluster_id
    with connect() as conn:  # restore the seeded cluster exactly
        conn.execute("""DELETE FROM trust_flags WHERE demand_cluster_id = %s
                        AND citizen_request_id IS NULL""", (cluster_id,))
        conn.execute("""DELETE FROM approvals WHERE recommendation_id IN
                        (SELECT id FROM recommendations WHERE demand_cluster_id = %s)""",
                     (cluster_id,))
        conn.execute("""UPDATE run_traces SET joined_recommendation_id = NULL
                        WHERE joined_recommendation_id IN
                        (SELECT id FROM recommendations WHERE demand_cluster_id = %s)""",
                     (cluster_id,))
        conn.execute("DELETE FROM recommendations WHERE demand_cluster_id = %s",
                     (cluster_id,))
        conn.execute("""UPDATE demand_clusters SET confidence = %s,
                        confidence_reason = %s, status = 'active' WHERE id = %s""",
                     (*confidence, cluster_id))
        conn.commit()
    cleanup_test_state()


def test_300_request_attack_is_flagged_and_rank_holds(kothrud):
    client = TestClient(app)
    with connect() as conn:
        before = _water_ranking(conn)
    assert before[0][0] == "Velhe"

    out = spam_attack.attack(
        count=300, place="Kothrud", source_prefix="test-spam-", workers=1,
        post=lambda path, body: client.post(path, json=body).status_code)
    assert out == {**out, "accepted": 300, "failed": 0}

    body = next(c for c in client.get("/api/clusters").json() if c["id"] == kothrud)
    assert body["member_count"] == 500 + 300
    # Flags are visible through the API; the burst is excluded from volume.
    assert body["trust"]["excluded"] >= 290
    assert body["counted_volume"] <= 500 + 10
    assert body["trust"]["open_cluster_flags"] == 1  # the spike
    flags = client.get("/api/trust/flags", params={"cluster_id": kothrud}).json()
    assert {f["rule"] for f in flags} >= {"duplicate_burst", "cluster_spike"}
    # Rank unchanged: the underserved village still outranks Kothrud.
    with connect() as conn:
        after = _water_ranking(conn)
    assert [n for n, _ in after] == [n for n, _ in before]
    # One gate item for the whole attack (gate consolidation, D19).
    with connect() as conn:
        (drafts,) = conn.execute(
            "SELECT count(*) FROM recommendations WHERE demand_cluster_id = %s",
            (kothrud,)).fetchone()
    assert drafts == 1
