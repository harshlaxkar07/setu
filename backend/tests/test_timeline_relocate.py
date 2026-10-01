"""Citizen timeline and location follow-up (enhancements tasks 6.1–6.2)."""
import json

import pytest
from fastapi.testclient import TestClient

from app import gemini, pipeline
from app.main import app
from app.stages import locate as locate_stage
from tests.conftest_a import (
    BASE_LAT,
    BASE_LON,
    cleanup_test_state,
    connect,
    ensure_pool,
    make_cluster,
    offset_point,
    reviewer_headers,
)
from tests.test_pipeline import RECOMMEND_JSON, _site

CONV = "test-timeline-conversation"


@pytest.fixture(scope="module")
def client():
    ensure_pool()
    yield TestClient(app)
    cleanup_test_state()


def _understand(mention: str):
    return json.dumps({"category": "water_infrastructure", "urgency": "high",
                       "summary": "No water for weeks", "detected_language": "Hindi",
                       "raw_location_mention": mention})


def _mock(monkeypatch, *, mention: str, lonlat=None, embedding=None):
    monkeypatch.setattr(gemini, "_live_call", lambda p, i=None:
                        RECOMMEND_JSON if p.startswith("You are drafting ONE")
                        else _understand(mention))
    monkeypatch.setattr(locate_stage, "MIN_INTERVAL_S", 0.0)
    result = ([] if lonlat is None else
              [{"lat": str(lonlat[1]), "lon": str(lonlat[0]),
                "display_name": "Test", "addresstype": "village"}])
    monkeypatch.setattr(locate_stage, "_live_transport", lambda q: result)
    monkeypatch.setattr(locate_stage, "_live_embedder",
                        lambda t: embedding or [0.03] * 768)


def _submit(client) -> str:
    r = client.post("/api/requests/text", json={"text": "test paani nahi", "conversation_id": CONV})
    return r.json()["id"]


def _states(client, rid) -> dict:
    return {s["key"]: s for s in client.get(f"/api/requests/{rid}/timeline").json()["stages"]}


def test_grouped_request_awaiting_review(client, monkeypatch):
    site = offset_point(BASE_LON, BASE_LAT, east_m=10_000 * next(_site))
    with connect() as conn:
        make_cluster(conn, lonlat=site, member_embeddings=[[0.03] * 768] * 3)
    _mock(monkeypatch, mention="Testpur", lonlat=site)
    rid = _submit(client)  # TestClient runs the pipeline as a background task
    st = _states(client, rid)
    assert [st[k]["state"] for k in ("received", "understood", "grouped")] == ["done"] * 3
    assert st["grouped"]["others"] == 3
    assert st["under_review"]["state"] == "current"
    assert st["published"]["state"] == "pending" and st["resolved"]["state"] == "pending"


def test_published_then_resolved_request(client, monkeypatch):
    site = offset_point(BASE_LON, BASE_LAT, east_m=10_000 * next(_site))
    _mock(monkeypatch, mention="Testpur", lonlat=site)
    rid = _submit(client)
    with connect() as conn:
        thread, cluster = conn.execute(
            """SELECT thread_id, (SELECT demand_cluster_id::text FROM recommendations
                                  WHERE thread_id = rt.thread_id)
               FROM run_traces rt WHERE citizen_request_id = %s""", (rid,)).fetchone()
    pipeline.resume_gate(thread, "approved", "Test Reviewer")
    st = _states(client, rid)
    assert st["published"]["state"] == "done" and st["resolved"]["state"] == "current"
    assert client.post(f"/api/clusters/{cluster}/resolve",
                       headers=reviewer_headers()).status_code == 200
    st = _states(client, rid)
    assert all(s["state"] == "done" for s in st.values())
    assert st["resolved"]["verified"] is False  # a claim, not yet verified


def _velhe(conn):
    return conn.execute(
        """SELECT dc.id::text, dc.member_count,
                  (SELECT gr.embedding::text FROM cluster_memberships cm
                   JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
                   WHERE cm.demand_cluster_id = dc.id LIMIT 1)
           FROM demand_clusters dc JOIN region_profiles rp
             ON ST_Contains(rp.boundary, dc.centroid)
           WHERE dc.category = 'water_infrastructure' AND rp.name = 'Velhe'""").fetchone()


def test_follow_up_answer_relocates_and_resumes(client, monkeypatch):
    with connect() as conn:
        velhe_id, velhe_members, emb = _velhe(conn)
    _mock(monkeypatch, mention="Zzyzx Nowhere", embedding=json.loads(emb))
    rid = _submit(client)

    status = client.get(f"/api/requests/{rid}/status").json()
    assert status["needs_location"] is True
    assert status["status"] == "needs_retry"  # halted before Fuse, not dropped
    st = _states(client, rid)
    assert st["grouped"]["state"] == "current"
    with connect() as conn:
        (placeholder,) = conn.execute(
            """SELECT cm.demand_cluster_id::text FROM cluster_memberships cm
               JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
               JOIN structured_requests sr ON sr.id = gr.structured_request_id
               WHERE sr.citizen_request_id = %s""", (rid,)).fetchone()

    # Someone else's conversation cannot answer for this request.
    assert client.post(f"/api/requests/{rid}/location",
                       json={"answer": "Velhe", "conversation_id": "test-intruder-x"}
                       ).status_code == 404

    out = client.post(f"/api/requests/{rid}/location",
                      json={"answer": "वेल्हे", "conversation_id": CONV}).json()
    assert out["resolved"] is True and out["cluster_id"] == velhe_id
    assert out["pipeline_resumed"] is True
    with connect() as conn:
        assert _velhe(conn)[1] == velhe_members + 1
        gone = conn.execute("SELECT 1 FROM demand_clusters WHERE id = %s",
                            (placeholder,)).fetchone()
        assert gone is None  # placeholder cluster removed, counts exact
        run_status, thread = conn.execute(
            """SELECT status::text, thread_id FROM run_traces
               WHERE citizen_request_id = %s""", (rid,)).fetchone()
    assert run_status == "awaiting_approval"
    assert "needs_location" not in client.get(f"/api/requests/{rid}/status").json()
    assert _states(client, rid)["grouped"]["state"] == "done"
    if pipeline.is_suspended_at_gate(thread):
        pipeline.resume_gate(thread, "rejected", "Test Reviewer")


def test_unlocatable_answer_keeps_request_flagged(client, monkeypatch):
    _mock(monkeypatch, mention="Zzyzx Nowhere")
    rid = _submit(client)
    out = client.post(f"/api/requests/{rid}/location",
                      json={"answer": "somewhere unknown qq", "conversation_id": CONV}).json()
    assert out["resolved"] is False
    status = client.get(f"/api/requests/{rid}/status").json()
    assert "needs_location" not in status  # asked once; stored and flagged
    with connect() as conn:
        (answer,) = conn.execute(
            "SELECT answer FROM location_followups WHERE citizen_request_id = %s",
            (rid,)).fetchone()
    assert answer == "somewhere unknown qq"


def test_already_located_request_cannot_be_relocated(client, monkeypatch):
    site = offset_point(BASE_LON, BASE_LAT, east_m=10_000 * next(_site))
    _mock(monkeypatch, mention="Testpur", lonlat=site)
    rid = _submit(client)
    r = client.post(f"/api/requests/{rid}/location",
                    json={"answer": "Velhe", "conversation_id": CONV})
    assert r.status_code == 409
