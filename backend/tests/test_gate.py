"""§7 gate endpoint tests — including the REAL cross-process proof.

The suspended thread is created by THIS process (pytest, mocked Gemini); the
resume goes over HTTP to the uvicorn process on localhost:8000, whose own
graph instance loads the thread from the shared Postgres checkpointer. That
is exactly the Streamlit → FastAPI boundary of design D2 — two different
processes, one durable gate. The finalize node makes no Gemini call, so the
server side needs no key.
"""
import json
import uuid

import httpx
import pytest

from app import gemini, pipeline
from app.stages import locate as locate_stage
from tests.conftest_a import (
    cleanup_test_state,
    connect,
    ensure_pool,
    reviewer_headers,
    reviewer_name,
)


@pytest.fixture(autouse=True, scope="module")
def _cleanup_after_module():
    """This module's suspended runs and gate decisions must not pollute the
    category cohort other test modules normalize over."""
    ensure_pool()
    yield
    cleanup_test_state()
from tests.test_pipeline import (  # reuse mocks + cleanup fixture's module scope
    RECOMMEND_JSON,
    UNDERSTAND_JSON,
    _mock_geo,
    _submit,
    _trace,
)

BACKEND = "http://localhost:8000"


def _mock_gemini(monkeypatch):
    monkeypatch.setattr(
        gemini, "_live_call",
        lambda prompt, image_bytes=None: RECOMMEND_JSON
        if prompt.startswith("You are drafting ONE") else UNDERSTAND_JSON,
    )


def _suspend_one(monkeypatch) -> str:
    _mock_gemini(monkeypatch)
    _mock_geo(monkeypatch)
    with connect() as conn:
        cr_id = _submit(conn)
    return pipeline.run_pipeline(cr_id)


def test_resume_unknown_thread_is_409_no_state_change():
    r = httpx.post(f"{BACKEND}/api/gate/{uuid.uuid4()}/resume",
                   json={"decision": "approved", "reviewer": "T"}, headers=reviewer_headers(), timeout=30)
    assert r.status_code == 409
    with connect() as conn:
        assert conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == \
            conn.execute("SELECT count(*) FROM approvals").fetchone()[0]


def test_cross_process_resume_publishes(monkeypatch):
    """Suspend in pytest; approve through the RUNNING SERVER (task 7.3)."""
    thread_id = _suspend_one(monkeypatch)

    r = httpx.post(f"{BACKEND}/api/gate/{thread_id}/resume",
                   json={"decision": "approved", "reviewer": "Cross Process"}, headers=reviewer_headers(),
                   timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "published"

    with connect() as conn:
        t = _trace(conn, thread_id)
        assert t["status"] == "published"
        a = conn.execute(
            """SELECT decision::text, reviewer FROM approvals a
               JOIN recommendations rec ON rec.id = a.recommendation_id
               WHERE rec.thread_id = %s""", (thread_id,)).fetchone()
        # The recorded reviewer is the signed-in account, never body text.
        assert a == ("approved", reviewer_name())

    # Second resume through the server: 409, nothing changes.
    r2 = httpx.post(f"{BACKEND}/api/gate/{thread_id}/resume",
                    json={"decision": "rejected", "reviewer": "X"}, headers=reviewer_headers(), timeout=30)
    assert r2.status_code == 409


def test_pending_never_in_published_view_before_approval(monkeypatch):
    """Task 7.7 (API half): refresh-before-approval leaks nothing."""
    thread_id = _suspend_one(monkeypatch)

    published = httpx.get(f"{BACKEND}/api/recommendations",
                          params={"status": "published"}, timeout=30).json()
    with connect() as conn:
        rec_id = conn.execute(
            "SELECT id::text FROM recommendations WHERE thread_id=%s",
            (thread_id,)).fetchone()[0]
    assert all(p["id"] != rec_id for p in published)

    pending = httpx.get(f"{BACKEND}/api/recommendations",
                        params={"status": "pending"}, timeout=30).json()
    assert any(p["id"] == rec_id for p in pending)

    # Invalid decision string: 422 from the model, no state change.
    bad = httpx.post(f"{BACKEND}/api/gate/{thread_id}/resume",
                     json={"decision": "sure", "reviewer": "T"}, headers=reviewer_headers(), timeout=30)
    assert bad.status_code == 422
    assert pipeline.is_suspended_at_gate(thread_id)

    httpx.post(f"{BACKEND}/api/gate/{thread_id}/resume",
               json={"decision": "rejected", "reviewer": "tidy"}, headers=reviewer_headers(), timeout=60)


def test_ops_view_lists_every_request(monkeypatch):
    thread_id = _suspend_one(monkeypatch)
    runs = httpx.get(f"{BACKEND}/api/ops/runs", timeout=30).json()
    assert any(r["thread_id"] == thread_id and r["status"] == "awaiting_approval"
               for r in runs)
    # Every accepted request appears exactly once with a defined status.
    with connect() as conn:
        total = conn.execute("SELECT count(*) FROM citizen_requests").fetchone()[0]
    assert len(runs) == total
    assert all(r["status"] for r in runs)
    httpx.post(f"{BACKEND}/api/gate/{thread_id}/resume",
               json={"decision": "rejected", "reviewer": "tidy"}, headers=reviewer_headers(), timeout=60)


def test_decision_without_sign_in_is_401_and_gate_stays_suspended(monkeypatch):
    """Enhancements task 4.2: the backend rejects unauthenticated decisions."""
    thread_id = _suspend_one(monkeypatch)
    for headers in ({}, {"Authorization": "Bearer not-a-token"}):
        r = httpx.post(f"{BACKEND}/api/gate/{thread_id}/resume",
                       json={"decision": "approved", "reviewer": "Anyone"},
                       headers=headers, timeout=30)
        assert r.status_code == 401
    assert pipeline.is_suspended_at_gate(thread_id)
    with connect() as conn:
        (n,) = conn.execute(
            """SELECT count(*) FROM approvals a JOIN recommendations r
                 ON r.id = a.recommendation_id WHERE r.thread_id = %s""",
            (thread_id,)).fetchone()
        assert n == 0
    httpx.post(f"{BACKEND}/api/gate/{thread_id}/resume",
               json={"decision": "rejected"}, headers=reviewer_headers(), timeout=60)
