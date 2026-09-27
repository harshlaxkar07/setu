"""Citizen intake API + page tests (tasks 3.1-3.5, 3.8).

TestClient is used WITHOUT the lifespan context: tests open the shared pool
themselves and never close it, so any number of test files can follow. The
pipeline background task is either monkeypatched out (pure persistence tests)
or run with every external dependency injected/mocked — never live Gemini,
never live Nominatim.
"""
import json
import os
import uuid
from pathlib import Path

import psycopg.errors
import pytest
from fastapi.testclient import TestClient

from app import gemini as gemini_mod
from app.main import app
from app.routers import requests as requests_router
from app.stages import locate as locate_mod
from app.stages import understand as understand_mod
from tests.conftest_a import cleanup_test_rows, connect, ensure_pool

VALID_EXTRACTION = {
    "category": "water_infrastructure",
    "urgency": "high",
    "summary": "Drinking water has not been supplied for weeks",
    "detected_language": "Hinglish",
    "raw_location_mention": "Testwadi",
}


@pytest.fixture(scope="module")
def client():
    ensure_pool()
    return TestClient(app)


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini_mod, "FIXTURE_DIR", tmp_path)
    monkeypatch.setattr(locate_mod, "FIXTURE_DIR", tmp_path)
    c = connect()
    yield c
    c.rollback()
    cleanup_test_rows(c)
    c.close()


def conv_id() -> str:
    return f"test-conv-{uuid.uuid4()}"


def no_pipeline(monkeypatch):
    """Silence the background pipeline for pure persistence tests."""
    monkeypatch.setattr(requests_router, "_kick_pipeline", lambda cr_id: None)


# ------------------------------------------------------------------- text

def test_text_submission_persists_exact_text(client, conn, monkeypatch):
    no_pipeline(monkeypatch)
    cid = conv_id()
    text = "paani nahi aa raha hai hamare gaon mein kai hafton se"
    res = client.post("/api/requests/text",
                      json={"text": text, "conversation_id": cid})
    assert res.status_code == 201
    rid = res.json()["id"]
    row = conn.execute(
        """SELECT channel, raw_text, audio_path, submitter_ref
           FROM citizen_requests WHERE id = %s""", (rid,)).fetchone()
    assert row == ("text", text, None, cid)


def test_same_conversation_same_pseudonymous_ref(client, conn, monkeypatch):
    """Two messages in one conversation share one submitter_ref, and no
    name/phone/identity is stored anywhere (citizen-intake spec)."""
    no_pipeline(monkeypatch)
    cid = conv_id()
    r1 = client.post("/api/requests/text",
                     json={"text": "test pehla message", "conversation_id": cid})
    r2 = client.post("/api/requests/text",
                     json={"text": "test doosra message", "conversation_id": cid})
    refs = conn.execute(
        "SELECT submitter_ref FROM citizen_requests WHERE id IN (%s, %s)",
        (r1.json()["id"], r2.json()["id"])).fetchall()
    assert refs == [(cid,), (cid,)]


# ------------------------------------------------------------------ voice

def test_voice_submission_stores_audio_and_row(client, conn, monkeypatch):
    no_pipeline(monkeypatch)
    cid = conv_id()
    payload = b"\x1aE\xdf\xa3 fake-webm-opus-bytes " + os.urandom(64)
    res = client.post(
        "/api/requests/voice",
        data={"conversation_id": cid},
        files={"audio": ("note.webm", payload, "audio/webm")})
    assert res.status_code == 201
    rid = res.json()["id"]
    channel, audio_path, submitter = conn.execute(
        "SELECT channel, audio_path, submitter_ref FROM citizen_requests WHERE id = %s",
        (rid,)).fetchone()
    assert channel == "voice" and submitter == cid
    assert Path(audio_path).read_bytes() == payload  # byte-for-byte persisted
    Path(audio_path).unlink()  # tidy the media volume


def test_empty_audio_rejected_without_row(client, conn, monkeypatch):
    no_pipeline(monkeypatch)
    res = client.post(
        "/api/requests/voice",
        data={"conversation_id": conv_id()},
        files={"audio": ("note.webm", b"", "audio/webm")})
    assert res.status_code == 400


# --------------------------------------------------- persist-first posture

def test_stage_failure_leaves_raw_request_and_audio_intact(client, conn,
                                                           monkeypatch):
    """Task 3.4: a forced downstream failure never removes or alters the raw
    CitizenRequest; the run halts visibly as needs_retry."""
    def boom(conn_, cr_id, **kw):
        raise RuntimeError("forced downstream failure")

    monkeypatch.setattr(understand_mod, "run", boom)
    cid = conv_id()
    payload = b"\x1aE\xdf\xa3 audio-that-must-survive"
    res = client.post(
        "/api/requests/voice",
        data={"conversation_id": cid},
        files={"audio": ("note.webm", payload, "audio/webm")})
    assert res.status_code == 201
    rid = res.json()["id"]

    # raw row + media file intact after the (synchronously-run) failing task
    audio_path, = conn.execute(
        "SELECT audio_path FROM citizen_requests WHERE id = %s", (rid,)).fetchone()
    assert Path(audio_path).read_bytes() == payload
    status = client.get(f"/api/requests/{rid}/status").json()
    assert status == {"status": "needs_retry", "receipt": None}
    Path(audio_path).unlink()


# -------------------------------------------------------------- immutability

def test_no_http_mutation_path_exists(client, conn, monkeypatch):
    no_pipeline(monkeypatch)
    rid = client.post("/api/requests/text",
                      json={"text": "test amar rahe",
                            "conversation_id": conv_id()}).json()["id"]
    for method in ("put", "patch", "delete"):
        r = getattr(client, method)(f"/api/requests/{rid}")
        assert r.status_code in (404, 405)  # no such endpoint at all
    row = conn.execute(
        "SELECT raw_text FROM citizen_requests WHERE id = %s", (rid,)).fetchone()
    assert row == ("test amar rahe",)


def test_db_trigger_rejects_update_and_delete(client, conn, monkeypatch):
    no_pipeline(monkeypatch)
    rid = client.post("/api/requests/text",
                      json={"text": "test atal", "conversation_id": conv_id()}
                      ).json()["id"]
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("UPDATE citizen_requests SET raw_text = 'x' WHERE id = %s",
                     (rid,))
    conn.rollback()
    with pytest.raises(psycopg.errors.RaiseException):
        conn.execute("DELETE FROM citizen_requests WHERE id = %s", (rid,))
    conn.rollback()


# --------------------------------------------------------- status & receipt

def test_status_unknown_request_404(client):
    assert client.get(f"/api/requests/{uuid.uuid4()}/status").status_code == 404
    assert client.get("/api/requests/not-a-uuid/status").status_code == 404


def test_receipt_reflects_extraction_after_pipeline(client, conn, monkeypatch):
    """Task 3.8 backend half: the status poll serves the understood category,
    urgency, summary and language once Understand completes."""
    real_understand, real_locate = understand_mod.run, locate_mod.run

    def understood(conn_, cr_id, **kw):
        return real_understand(
            conn_, cr_id,
            _caller=lambda p, image_bytes=None: json.dumps(VALID_EXTRACTION))

    def located(conn_, sr_id, **kw):
        return real_locate(
            conn_, sr_id,
            _transport=lambda q: [{"lat": "18.9", "lon": "74.3",
                                   "display_name": "Testwadi",
                                   "importance": 0.5, "addresstype": "village"}],
            _embedder=lambda t: [0.5] * 768)

    monkeypatch.setattr(locate_mod, "MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(understand_mod, "run", understood)
    monkeypatch.setattr(locate_mod, "run", located)
    # §7's graph runs past Cluster to the gate: Recommend must be mocked too
    # (tests never touch live Gemini), and the run ends awaiting approval.
    from app import gemini as gemini_mod
    monkeypatch.setattr(
        gemini_mod, "_live_call",
        lambda p, image_bytes=None: json.dumps({
            "intervention_text": "Evaluate a piped supply point.",
            "intervention_type": "water_supply_point_evaluation",
            "cited_indicators": ["population affected"],
        }) if p.startswith("You are drafting ONE") else json.dumps(VALID_EXTRACTION))

    res = client.post("/api/requests/text",
                      json={"text": f"test paani problem {uuid.uuid4()}",
                            "conversation_id": conv_id()})
    body = client.get(f"/api/requests/{res.json()['id']}/status").json()
    assert body["receipt"] == {
        "category": "water_infrastructure",
        "urgency": "high",
        "summary": VALID_EXTRACTION["summary"],
        "detected_language": "Hinglish",
    }
    assert body["status"] == "awaiting_approval"

    # Leave no suspended gate or cohort pollution behind.
    from tests.conftest_a import cleanup_test_state
    cleanup_test_state()


def test_status_before_processing_is_received(client, conn, monkeypatch):
    no_pipeline(monkeypatch)
    rid = client.post("/api/requests/text",
                      json={"text": "test abhi aya",
                            "conversation_id": conv_id()}).json()["id"]
    assert client.get(f"/api/requests/{rid}/status").json() == {
        "status": "received", "receipt": None}


# ------------------------------------------------------------ citizen page

def test_citizen_page_serves_bilingual_no_pii_widget(client):
    """Task 3.1/3.5 static checks: page loads standalone from the backend,
    Devanagari-primary chrome with Noto Sans Devanagari, and NO PII inputs."""
    res = client.get("/citizen/")
    assert res.status_code == 200
    html = res.text
    assert "Noto+Sans+Devanagari" in html          # never a silent Latin fallback
    assert "अपनी समस्या बताइए" in html               # Hindi-primary chrome
    assert "Tell us about your problem" in html    # English subtitle
    # exactly one input: the text fallback — no name/phone/identity fields
    assert html.count("<input") == 1
    for pii in ("type=\"tel\"", "type=\"email\"", "autocomplete=\"name\""):
        assert pii not in html
    # static assets resolve
    assert client.get("/citizen/app.js").status_code == 200
    assert client.get("/citizen/styles.css").status_code == 200
    js = client.get("/citizen/app.js").text
    assert "audio/webm;codecs=opus" in js
    assert "localStorage" in js and "conversation_id" in js
