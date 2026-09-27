"""§8 verification bolt-on tests (tasks 8.1–8.5).

Runs inside the backend container against the seeded database. NEVER live
Gemini: `app.gemini._live_call` is monkeypatched (call_gemini's retry-once
posture stays real), and STT is monkeypatched so no Whisper model loads.
Fixture recording and media both go to tmp_path, so the repo's fixture store
and the media volume are untouched. Every row uses 'test-' submitter_refs;
the module-scoped teardown restores the seeded state.
"""
import base64
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app import gemini as gemini_mod
from app import stt as stt_mod
from app.main import app
from app.routers import verification as verification_router
from app.stages import verify as verify_stage
from tests.conftest_a import (
    BASE_LAT,
    BASE_LON,
    cleanup_test_state,
    connect,
    ensure_pool,
    make_citizen_request,
    make_cluster,
    make_geocoded_request,
    make_structured_request,
    unit_vector,
)

ORIGINAL_SUMMARY = "No drinking water supply in the village for several weeks"

MATCH_JSON = json.dumps(
    {"result": "match", "reason": "water is visibly flowing from the tap"})
MISMATCH_JSON = json.dumps(
    {"result": "mismatch", "reason": "the after photo still shows a dry, cracked pipe"})
NEEDS_REVIEW_JSON = json.dumps(
    {"result": "needs_human_review", "reason": "cannot judge from this evidence"})

# A real (tiny) PNG — any generated image bytes are fine for the vision mock.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
WEBM_BYTES = b"\x1aE\xdf\xa3fake-opus-followup-audio"


@pytest.fixture(autouse=True, scope="module")
def _cleanup_after_module():
    ensure_pool()
    yield
    cleanup_test_state()


@pytest.fixture(scope="module")
def client():
    ensure_pool()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    """No fixture recording into the repo store, no media into the volume."""
    monkeypatch.setattr(gemini_mod, "FIXTURE_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(verification_router, "MEDIA_DIR", tmp_path / "media")


@pytest.fixture()
def conn():
    c = connect()
    yield c
    c.rollback()
    c.close()


# ---------------------------------------------------------------- helpers

def conv_id() -> str:
    return f"test-verify-{uuid.uuid4().hex[:12]}"


def make_resolved_cluster(conn, status: str = "resolved_unverified") -> str:
    cid = make_cluster(conn, lonlat=(BASE_LON, BASE_LAT),
                       summary=ORIGINAL_SUMMARY,
                       member_embeddings=[unit_vector(0)])
    conn.execute("UPDATE demand_clusters SET status = %s WHERE id = %s",
                 (status, cid))
    conn.commit()
    return cid


def post_followup(client, cluster_id: str, conv: str, *,
                  photos: int = 0, voice: bool = False):
    files = [("photos", (f"photo{i}.png", PNG_BYTES, "image/png"))
             for i in range(photos)]
    if voice:
        files.append(("voice", ("note.webm", WEBM_BYTES, "audio/webm")))
    return client.post(f"/api/verification/{cluster_id}",
                       files=files or None,
                       data={"conversation_id": conv})


def record_row(conn, record_id: str) -> dict:
    row = conn.execute(
        """SELECT result::text, flagged, media_paths, voice_path,
                  submitter_ref, review_decision, review_reviewer, reviewed_at
           FROM verification_records WHERE id = %s""",
        (record_id,),
    ).fetchone()
    return {"result": row[0], "flagged": row[1], "media_paths": row[2],
            "voice_path": row[3], "submitter_ref": row[4],
            "review_decision": row[5], "review_reviewer": row[6],
            "reviewed_at": row[7]}


def cluster_state(conn, cluster_id: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT status::text, confidence::text FROM demand_clusters WHERE id = %s",
        (cluster_id,),
    ).fetchone()
    return row[0], row[1]


def mock_gemini(monkeypatch, response: str):
    """Recording mock for the vision/text plausibility call."""
    calls: list[tuple[str, bytes | None]] = []

    def fake(prompt: str, image_bytes=None) -> str:
        calls.append((prompt, image_bytes))
        return response

    monkeypatch.setattr(gemini_mod, "_live_call", fake)
    return calls


def mock_stt(monkeypatch, text: str = "paani ab theek se aa raha hai"):
    monkeypatch.setattr(stt_mod, "transcribe", lambda path: (text, "Hindi"))


def verify_traces(conn, record_id: str) -> list[dict]:
    """RunTraces whose stages contain a Verify entry for this record."""
    rows = conn.execute(
        """SELECT rt.citizen_request_id::text, rt.status::text, rt.stages
           FROM run_traces rt
           WHERE rt.stages @> %s::jsonb""",
        (json.dumps([{"stage": "Verify", "input_ref": record_id}]),),
    ).fetchall()
    return [{"citizen_request_id": r[0], "status": r[1], "stages": r[2]}
            for r in rows]


# --------------------------------------------------- 8.1: mark-resolved

def test_mark_resolved_transitions_published_cluster_only(client, conn):
    """Resolution is a claim: published → resolved_unverified, 409 otherwise."""
    cid = make_cluster(conn, lonlat=(BASE_LON, BASE_LAT),
                       summary=ORIGINAL_SUMMARY,
                       member_embeddings=[unit_vector(0)])
    conn.execute("UPDATE demand_clusters SET status = 'published' WHERE id = %s",
                 (cid,))
    conn.commit()

    r = client.post(f"/api/clusters/{cid}/resolve")
    assert r.status_code == 200
    assert r.json() == {"id": cid, "status": "resolved_unverified"}
    assert cluster_state(conn, cid)[0] == "resolved_unverified"

    # Resolution alone never verifies: it stays resolved_unverified, and a
    # second resolve is refused rather than faking a transition.
    assert client.post(f"/api/clusters/{cid}/resolve").status_code == 409
    assert cluster_state(conn, cid)[0] == "resolved_unverified"


# ----------------------------------- 8.2: prompt rides the status poll

def test_status_poll_carries_prompt_only_after_resolution(client, conn):
    conv = conv_id()
    cr = make_citizen_request(conn, submitter=conv)
    sr = make_structured_request(conn, cr)
    gr = make_geocoded_request(conn, sr, lonlat=(BASE_LON, BASE_LAT),
                               embedding=unit_vector(0))
    cid = make_cluster(conn, lonlat=(BASE_LON, BASE_LAT),
                       summary=ORIGINAL_SUMMARY,
                       member_embeddings=[unit_vector(0)])
    conn.execute(
        """INSERT INTO cluster_memberships
             (geocoded_request_id, demand_cluster_id, similarity_score)
           VALUES (%s, %s, 0.95)""",
        (gr, cid),
    )
    conn.execute("UPDATE demand_clusters SET status = 'published' WHERE id = %s",
                 (cid,))
    conn.commit()

    # Before resolution: no verification prompt (spec "No prompt before
    # resolution") — and the pre-§8 payload shape is untouched.
    body = client.get(f"/api/requests/{cr}/status").json()
    assert "verification_prompts" not in body

    conn.execute(
        "UPDATE demand_clusters SET status = 'resolved_unverified' WHERE id = %s",
        (cid,))
    conn.commit()

    body = client.get(f"/api/requests/{cr}/status").json()
    prompts = body.get("verification_prompts")
    assert prompts is not None
    assert {"cluster_id": cid, "category": "water_infrastructure",
            "summary": ORIGINAL_SUMMARY, "status": "resolved_unverified"} \
        in prompts


def test_status_poll_no_prompt_for_uninvolved_conversation(client, conn):
    """The prompt targets contributing conversations only (design D4 step 5)."""
    make_resolved_cluster(conn)  # resolved, but this conversation is not in it
    conv = conv_id()
    cr = make_citizen_request(conn, submitter=conv)
    body = client.get(f"/api/requests/{cr}/status").json()
    assert "verification_prompts" not in body


# ------------------------- 8.3: record creation, pseudonymity, immutability

def test_followup_creates_pending_record_with_immutable_media(client, conn,
                                                              monkeypatch):
    """The record starts pending until the check completes; raw media is
    stored byte-identical; the submitter stays the pseudonymous conv id."""
    monkeypatch.setattr(verification_router, "_kick_verification",
                        lambda record_id: None)  # keep it pending
    cid = make_resolved_cluster(conn)
    conv = conv_id()

    r = post_followup(client, cid, conv, photos=2, voice=True)
    assert r.status_code == 201
    body = r.json()
    assert body["result"] == "pending"
    assert body["demand_cluster_id"] == cid

    rec = record_row(conn, body["id"])
    assert rec["result"] == "pending"
    assert rec["flagged"] is False
    assert rec["submitter_ref"] == conv  # pseudonymous, cluster-scoped
    assert len(rec["media_paths"]) == 2
    from pathlib import Path
    for p in rec["media_paths"]:
        assert Path(p).read_bytes() == PNG_BYTES  # stored unmodified
    assert Path(rec["voice_path"]).read_bytes() == WEBM_BYTES


def test_followup_rejected_unless_cluster_resolved(client, conn, monkeypatch):
    """409 for non-resolved states, 404 unknown, 400 without any media."""
    monkeypatch.setattr(verification_router, "_kick_verification",
                        lambda record_id: None)  # never a live check here
    for status in ("active", "published"):
        cid = make_cluster(conn, lonlat=(BASE_LON, BASE_LAT),
                           summary=ORIGINAL_SUMMARY,
                           member_embeddings=[unit_vector(0)])
        conn.execute("UPDATE demand_clusters SET status = %s WHERE id = %s",
                     (status, cid))
        conn.commit()
        assert post_followup(client, cid, conv_id(),
                             photos=1).status_code == 409
        assert conn.execute(
            "SELECT count(*) FROM verification_records WHERE demand_cluster_id = %s",
            (cid,)).fetchone()[0] == 0

    assert post_followup(client, str(uuid.uuid4()), conv_id(),
                         photos=1).status_code == 404
    assert post_followup(client, "not-a-uuid", conv_id(),
                         photos=1).status_code == 404

    cid = make_resolved_cluster(conn)
    assert post_followup(client, cid, conv_id()).status_code == 400

    # A follow-up for an already-verified cluster is still accepted.
    cid2 = make_resolved_cluster(conn, status="resolved_verified")
    assert post_followup(client, cid2, conv_id(), photos=1).status_code == 201


# --------------------------------------- 8.4: plausibility check outcomes

def test_photo_match_confirms_cluster_and_traces(client, conn, monkeypatch):
    calls = mock_gemini(monkeypatch, MATCH_JSON)
    cid = make_resolved_cluster(conn)
    conv = conv_id()
    cr = make_citizen_request(conn, submitter=conv)  # the conversation's own

    r = post_followup(client, cid, conv, photos=1)
    assert r.status_code == 201
    record_id = r.json()["id"]

    # Vision path, judged against the ORIGINAL complaint summary.
    assert len(calls) == 1
    prompt, image_bytes = calls[0]
    assert image_bytes == PNG_BYTES
    assert ORIGINAL_SUMMARY in prompt

    rec = record_row(conn, record_id)
    assert rec["result"] == "match"
    assert rec["flagged"] is False  # confirmed, not flagged
    status, confidence = cluster_state(conn, cid)
    assert status == "resolved_verified"  # match → resolved_verified
    assert confidence == "high"  # ConfidenceLevel stays high

    # Verify stage execution recorded as a RunTrace on the submitting
    # conversation's request (pipeline-orchestration spec).
    traces = verify_traces(conn, record_id)
    assert traces and traces[0]["citizen_request_id"] == cr
    entry = [s for s in traces[0]["stages"] if s["stage"] == "Verify"][0]
    assert entry["result"] == "match"
    assert "duration_ms" in entry


def test_mismatched_before_after_pair_is_flagged_never_autoclosed(
        client, conn, monkeypatch):
    """Task 8.5 definition of done: a deliberately mismatched before/after
    photo pair is flagged for human review — not auto-approved, not closed."""
    calls = mock_gemini(monkeypatch, MISMATCH_JSON)
    cid = make_resolved_cluster(conn)

    r = post_followup(client, cid, conv_id(), photos=2)  # before/after pair
    assert r.status_code == 201
    record_id = r.json()["id"]
    assert len(calls) == 1

    rec = record_row(conn, record_id)
    assert rec["result"] == "mismatch"
    assert rec["flagged"] is True
    # Never auto-closed: the cluster stays resolved_unverified.
    assert cluster_state(conn, cid)[0] == "resolved_unverified"

    # Traced even though this conversation never filed a complaint: the
    # trace attaches to the cluster's latest member request (NOT NULL FK).
    traces = verify_traces(conn, record_id)
    assert traces and traces[0]["citizen_request_id"] is not None


def test_photo_needs_human_review_is_flagged(client, conn, monkeypatch):
    mock_gemini(monkeypatch, NEEDS_REVIEW_JSON)
    cid = make_resolved_cluster(conn)
    record_id = post_followup(client, cid, conv_id(), photos=1).json()["id"]
    rec = record_row(conn, record_id)
    assert rec["result"] == "needs_human_review"
    assert rec["flagged"] is True
    assert cluster_state(conn, cid)[0] == "resolved_unverified"


def test_voice_match_uses_local_transcript_and_text_comparison(
        client, conn, monkeypatch):
    calls = mock_gemini(monkeypatch, MATCH_JSON)
    mock_stt(monkeypatch, "ab paani theek se aa raha hai, samasya hal ho gayi")
    cid = make_resolved_cluster(conn)

    record_id = post_followup(client, cid, conv_id(), voice=True).json()["id"]

    assert len(calls) == 1
    prompt, image_bytes = calls[0]
    assert image_bytes is None  # text comparison, no vision
    assert "ab paani theek se aa raha hai" in prompt  # local transcript
    assert ORIGINAL_SUMMARY in prompt

    assert record_row(conn, record_id)["result"] == "match"
    assert cluster_state(conn, cid)[0] == "resolved_verified"


def test_voice_mismatch_flagged(client, conn, monkeypatch):
    mock_gemini(monkeypatch, MISMATCH_JSON)
    mock_stt(monkeypatch, "paani abhi bhi nahi aa raha")
    cid = make_resolved_cluster(conn)
    record_id = post_followup(client, cid, conv_id(), voice=True).json()["id"]
    rec = record_row(conn, record_id)
    assert (rec["result"], rec["flagged"]) == ("mismatch", True)
    assert cluster_state(conn, cid)[0] == "resolved_unverified"


def test_voice_needs_human_review_flagged(client, conn, monkeypatch):
    mock_gemini(monkeypatch, NEEDS_REVIEW_JSON)
    mock_stt(monkeypatch)
    cid = make_resolved_cluster(conn)
    record_id = post_followup(client, cid, conv_id(), voice=True).json()["id"]
    rec = record_row(conn, record_id)
    assert (rec["result"], rec["flagged"]) == ("needs_human_review", True)
    assert cluster_state(conn, cid)[0] == "resolved_unverified"


def test_photo_plus_voice_takes_vision_path_with_transcript_context(
        client, conn, monkeypatch):
    calls = mock_gemini(monkeypatch, MATCH_JSON)
    mock_stt(monkeypatch, "naya nal lag gaya hai")
    cid = make_resolved_cluster(conn)

    post_followup(client, cid, conv_id(), photos=1, voice=True)

    assert len(calls) == 1
    prompt, image_bytes = calls[0]
    assert image_bytes == PNG_BYTES  # photo (vision) path wins
    assert "naya nal lag gaya hai" in prompt  # transcript as added context


def test_check_failure_after_retry_defaults_to_human_review(
        client, conn, monkeypatch):
    """Double Gemini failure → needs_human_review + flagged; NEVER match,
    submission retained, cluster untouched (verification spec)."""
    attempts = {"n": 0}

    def always_fail(prompt, image_bytes=None):
        attempts["n"] += 1
        raise RuntimeError("simulated vision API outage")

    monkeypatch.setattr(gemini_mod, "_live_call", always_fail)
    cid = make_resolved_cluster(conn)

    r = post_followup(client, cid, conv_id(), photos=1)
    assert r.status_code == 201
    record_id = r.json()["id"]

    assert attempts["n"] == 2  # exactly one retry
    rec = record_row(conn, record_id)
    assert rec["result"] == "needs_human_review"
    assert rec["flagged"] is True
    assert cluster_state(conn, cid)[0] == "resolved_unverified"
    # The submission is retained, media intact.
    from pathlib import Path
    assert Path(rec["media_paths"][0]).read_bytes() == PNG_BYTES
    # The trace records the failure without dropping the run.
    traces = verify_traces(conn, record_id)
    assert traces and any("check_error" in s for s in traces[0]["stages"])


# ------------------------------ 8.5: flag routing, review surface, review

def test_flag_persists_and_no_api_path_mutates_the_record(client, conn,
                                                          monkeypatch):
    """No automated path clears the flag; no endpoint edits media or record."""
    mock_gemini(monkeypatch, MISMATCH_JSON)
    cid = make_resolved_cluster(conn)
    record_id = post_followup(client, cid, conv_id(), photos=1).json()["id"]

    before = record_row(conn, record_id)
    assert before["flagged"] is True

    # There is deliberately no mutation surface for records or their media.
    for method in ("put", "patch", "delete"):
        resp = getattr(client, method)(f"/api/verifications/{record_id}")
        assert resp.status_code in (404, 405)
        resp = getattr(client, method)(f"/api/verification/{cid}")
        assert resp.status_code in (404, 405)

    after = record_row(conn, record_id)
    assert after["flagged"] is True  # persists until a human decides
    assert after["media_paths"] == before["media_paths"]
    from pathlib import Path
    assert Path(after["media_paths"][0]).read_bytes() == PNG_BYTES


def test_flagged_listing_is_pseudonymous_with_comparison_evidence(
        client, conn, monkeypatch):
    """GET /api/verifications: original summary rides along for side-by-side
    review; no submitter identity — not even the pseudonymous ref."""
    mock_gemini(monkeypatch, MISMATCH_JSON)
    cid = make_resolved_cluster(conn)
    conv = conv_id()
    record_id = post_followup(client, cid, conv, photos=2).json()["id"]

    listing = client.get("/api/verifications", params={"flagged": "true"}).json()
    mine = [r for r in listing if r["id"] == record_id]
    assert len(mine) == 1
    rec = mine[0]
    assert rec["demand_cluster_id"] == cid  # cluster-scoped
    assert rec["cluster_summary"] == ORIGINAL_SUMMARY  # the original complaint
    assert len(rec["media_paths"]) == 2  # the follow-up submission
    assert rec["result"] == "mismatch" and rec["flagged"] is True
    # Pseudonymity: no identity field of any kind in the payload.
    assert "submitter_ref" not in rec
    assert not any(k in rec for k in ("name", "phone", "handle", "citizen"))
    assert conv not in json.dumps(rec)


def test_review_confirm_resolved_clears_flag_and_verifies_cluster(
        client, conn, monkeypatch):
    mock_gemini(monkeypatch, MISMATCH_JSON)
    cid = make_resolved_cluster(conn)
    record_id = post_followup(client, cid, conv_id(), photos=1).json()["id"]

    r = client.post(f"/api/verifications/{record_id}/review",
                    json={"decision": "confirm_resolved",
                          "reviewer": "Block Officer Deshmukh"})
    assert r.status_code == 200
    body = r.json()
    assert body["flagged"] is False
    assert body["cluster_status"] == "resolved_verified"

    rec = record_row(conn, record_id)
    assert rec["flagged"] is False
    assert rec["review_decision"] == "confirm_resolved"
    assert rec["review_reviewer"] == "Block Officer Deshmukh"
    assert rec["reviewed_at"] is not None
    assert cluster_state(conn, cid)[0] == "resolved_verified"

    # The decision is retrievable afterwards through the listing.
    listing = client.get("/api/verifications").json()
    mine = [x for x in listing if x["id"] == record_id][0]
    assert mine["review_decision"] == "confirm_resolved"
    assert mine["review_reviewer"] == "Block Officer Deshmukh"
    assert mine["reviewed_at"] is not None


def test_review_reject_records_decision_cluster_stays_unverified(
        client, conn, monkeypatch):
    mock_gemini(monkeypatch, MISMATCH_JSON)
    cid = make_resolved_cluster(conn)
    record_id = post_followup(client, cid, conv_id(), photos=1).json()["id"]

    r = client.post(f"/api/verifications/{record_id}/review",
                    json={"decision": "reject_resolution",
                          "reviewer": "Block Officer Deshmukh"})
    assert r.status_code == 200
    assert r.json()["cluster_status"] == "resolved_unverified"

    rec = record_row(conn, record_id)
    # A recorded human decision resolves the flag either way…
    assert rec["flagged"] is False
    assert rec["review_decision"] == "reject_resolution"
    assert rec["reviewed_at"] is not None
    # …but a rejected resolution never verifies the cluster.
    assert cluster_state(conn, cid)[0] == "resolved_unverified"


def test_review_unknown_404_and_second_review_409(client, conn, monkeypatch):
    assert client.post(f"/api/verifications/{uuid.uuid4()}/review",
                       json={"decision": "confirm_resolved",
                             "reviewer": "X"}).status_code == 404
    assert client.post("/api/verifications/not-a-uuid/review",
                       json={"decision": "confirm_resolved",
                             "reviewer": "X"}).status_code == 404

    mock_gemini(monkeypatch, MISMATCH_JSON)
    cid = make_resolved_cluster(conn)
    record_id = post_followup(client, cid, conv_id(), photos=1).json()["id"]
    first = client.post(f"/api/verifications/{record_id}/review",
                        json={"decision": "reject_resolution", "reviewer": "A"})
    assert first.status_code == 200
    second = client.post(f"/api/verifications/{record_id}/review",
                         json={"decision": "confirm_resolved", "reviewer": "B"})
    assert second.status_code == 409
    # The first decision stands, unrewritten.
    rec = record_row(conn, record_id)
    assert rec["review_decision"] == "reject_resolution"
    assert rec["review_reviewer"] == "A"
