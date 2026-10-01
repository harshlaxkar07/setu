"""Assisted field-worker intake (enhancements task 6.5, design D11)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import requests as requests_router
from tests.conftest_a import cleanup_test_rows, connect, ensure_pool


@pytest.fixture()
def client(monkeypatch):
    ensure_pool()
    # Intake only: the pipeline is exercised elsewhere.
    monkeypatch.setattr(requests_router, "_kick_pipeline", lambda cr_id: None)
    yield TestClient(app)
    with connect() as conn:
        cleanup_test_rows(conn)


def _body(**kw):
    return {"text": "गाँव में हैंडपंप टूटा है", "conversation_id": "test-fieldworker-1",
            "assisted": True, "village": "Pabe", "households": 12,
            "idempotency_key": f"test-{uuid.uuid4()}", **kw}


def test_assisted_report_is_labelled_with_village_and_households(client):
    r = client.post("/api/requests/text", json=_body())
    assert r.status_code == 201
    with connect() as conn:
        channel, village, households = conn.execute(
            """SELECT channel::text, assisted_village, households_represented
               FROM citizen_requests WHERE id = %s""", (r.json()["id"],)).fetchone()
    assert (channel, village, households) == ("assisted", "Pabe", 12)


def test_replayed_queue_item_returns_the_original_request(client):
    body = _body()
    first = client.post("/api/requests/text", json=body).json()
    again = client.post("/api/requests/text", json=body).json()
    assert again["id"] == first["id"] and again["duplicate"] is True
    with connect() as conn:
        (n,) = conn.execute("SELECT count(*) FROM citizen_requests WHERE idempotency_key = %s",
                            (body["idempotency_key"],)).fetchone()
    assert n == 1


def test_assisted_report_needs_a_village(client):
    r = client.post("/api/requests/text", json=_body(village=None))
    assert r.status_code == 422


def test_no_personal_fields_are_accepted(client):
    r = client.post("/api/requests/text", json=_body(phone="9876543210", name="Sunita"))
    assert r.status_code == 201
    with connect() as conn:
        cols = {c.name for c in conn.execute(
            "SELECT * FROM citizen_requests WHERE id = %s", (r.json()["id"],)).description}
    assert not {"phone", "name"} & cols  # unknown fields are simply dropped


def test_village_is_the_location_when_the_text_names_none(client):
    from app.stages import locate
    from tests.conftest_a import make_structured_request
    cr = client.post("/api/requests/text", json=_body(village="Pabe")).json()["id"]
    with connect() as conn:
        sr = make_structured_request(conn, cr, mention="")
        gr = locate.run(conn, sr, _transport=lambda q: [],
                        _embedder=lambda t: [0.5] * 768)
        confidence, reason = conn.execute(
            "SELECT confidence, confidence_reason FROM geocoded_requests WHERE id = %s",
            (gr,)).fetchone()
    assert confidence == "medium" and "'Pabe'" in reason


def test_ordinary_submission_is_unchanged(client):
    r = client.post("/api/requests/text",
                    json={"text": "test paani", "conversation_id": "test-plain-conv-1"})
    assert r.status_code == 201 and "duplicate" not in r.json()
    with connect() as conn:
        (channel,) = conn.execute("SELECT channel::text FROM citizen_requests WHERE id=%s",
                                  (r.json()["id"],)).fetchone()
    assert channel == "text"
