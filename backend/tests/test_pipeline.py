"""§7 tests: the LangGraph pipeline, Publish Gate interrupt, retry posture.

Runs inside the backend container against the seeded database. No live
Gemini/Nominatim: `app.gemini._live_call` and `app.stages.locate` transports
are monkeypatched. The suite self-cleans (test- prefix) and re-runs
Fuse/Score over the seeded clusters afterwards so the stored seed scores are
restored to their canonical two-cluster-cohort values.
"""
import json
import uuid

import pytest

from app import db, gemini, pipeline
from app.constants import CATEGORY_WATER
from app.stages import locate as locate_stage
from tests.conftest_a import (
    BASE_LAT,
    BASE_LON,
    cleanup_test_state,
    connect,
    ensure_pool,
    offset_point,
)

UNDERSTAND_JSON = json.dumps({
    "category": CATEGORY_WATER,
    "urgency": "high",
    "summary": "No proper drinking water supply for several weeks",
    "detected_language": "Hindi",
    "raw_location_mention": "Velhe",
})
RECOMMEND_JSON = json.dumps({
    "intervention_text": "Evaluate installing a piped water supply point.",
    "intervention_type": "water_supply_point_evaluation",
    "cited_indicators": ["population affected", "historical investment"],
})


def _mock_gemini(monkeypatch, fail_stage: str | None = None,
                 fail_count: dict | None = None):
    """Dispatch mocked Gemini responses on prompt content; optionally fail."""
    def fake_live(prompt: str, image_bytes=None) -> str:
        drafting = prompt.startswith("You are drafting ONE")
        stage = "recommend" if drafting else "understand"
        if fail_stage == stage and fail_count and fail_count["n"] > 0:
            fail_count["n"] -= 1
            raise RuntimeError("simulated Gemini outage")
        return RECOMMEND_JSON if drafting else UNDERSTAND_JSON
    monkeypatch.setattr(gemini, "_live_call", fake_live)


_site = iter(range(1, 10_000))


def _mock_geo(monkeypatch, lonlat: tuple[float, float] | None = None):
    """Geocode every mention to `lonlat` — by default a fresh site per call,
    10 km apart, so each test founds its own cluster (one pending draft per
    cluster, enhancements D19, would otherwise make tests interfere)."""
    lon, lat = lonlat or offset_point(BASE_LON, BASE_LAT, east_m=10_000 * next(_site))
    monkeypatch.setattr(locate_stage, "MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(locate_stage, "_live_transport", lambda q: [{
        "lat": str(lat), "lon": str(lon),
        "display_name": "Test Playground, Pune, Maharashtra, India",
        "type": "village", "addresstype": "village",
    }])
    monkeypatch.setattr(locate_stage, "_live_embedder",
                        lambda text: [0.03] * 768)


def _submit(conn) -> str:
    row = conn.execute(
        """INSERT INTO citizen_requests (channel, raw_text, submitter_ref)
           VALUES ('text', %s, %s) RETURNING id""",
        ("test paani nahi aa raha", f"test-pipeline-{uuid.uuid4().hex[:8]}"),
    ).fetchone()
    conn.commit()
    return str(row[0])


def _trace(conn, thread_id: str) -> dict:
    row = conn.execute(
        """SELECT id::text, status::text, stages FROM run_traces
           WHERE thread_id = %s""", (thread_id,),
    ).fetchone()
    return {"id": row[0], "status": row[1], "stages": row[2]}


@pytest.fixture(autouse=True, scope="module")
def _restore_seed_scores():
    """After this module: purge test artifacts, restore canonical seed scores."""
    ensure_pool()
    yield
    cleanup_test_state()


def test_full_run_suspends_at_gate_with_complete_trace(monkeypatch):
    """Task 7.1/7.2: stages 1–6 run; the run durably suspends at the gate."""
    _mock_gemini(monkeypatch)
    _mock_geo(monkeypatch)
    with connect() as conn:
        cr_id = _submit(conn)

    thread_id = pipeline.run_pipeline(cr_id)

    with connect() as conn:
        t = _trace(conn, thread_id)
        assert t["status"] == "awaiting_approval"
        stages = [s["stage"] for s in t["stages"]]
        assert stages == ["Understand", "Locate", "Cluster", "Trust",
                          "Fuse", "Score", "Recommend"]
        assert all(s.get("duration_ms") is not None for s in t["stages"])
        rec = conn.execute(
            """SELECT status::text FROM recommendations WHERE thread_id=%s""",
            (thread_id,)).fetchone()
        assert rec[0] == "pending"
        # Suspended state is in the Postgres checkpointer (durable halt).
        assert pipeline.is_suspended_at_gate(thread_id)


def test_approve_publishes_and_second_resume_conflicts(monkeypatch):
    _mock_gemini(monkeypatch)
    _mock_geo(monkeypatch)
    with connect() as conn:
        cr_id = _submit(conn)
    thread_id = pipeline.run_pipeline(cr_id)

    out = pipeline.resume_gate(thread_id, "approved", "Test Reviewer")
    assert out["status"] == "published"
    with connect() as conn:
        t = _trace(conn, thread_id)
        assert t["status"] == "published"
        assert t["stages"][-1]["stage"] == "Publish Gate"
        a = conn.execute(
            """SELECT decision::text, reviewer FROM approvals a
               JOIN recommendations r ON r.id = a.recommendation_id
               WHERE r.thread_id = %s""", (thread_id,)).fetchone()
        assert a == ("approved", "Test Reviewer")
    with pytest.raises(pipeline.NotSuspended):
        pipeline.resume_gate(thread_id, "approved", "Test Reviewer")


def test_reject_is_terminal_and_deletes_nothing(monkeypatch):
    _mock_gemini(monkeypatch)
    _mock_geo(monkeypatch)
    with connect() as conn:
        cr_id = _submit(conn)
    thread_id = pipeline.run_pipeline(cr_id)
    out = pipeline.resume_gate(thread_id, "rejected", "Test Reviewer")
    assert out["status"] == "rejected"
    with connect() as conn:
        assert _trace(conn, thread_id)["status"] == "rejected"
        # Nothing deleted: raw request, cluster, scores all persist.
        kept = conn.execute(
            """SELECT count(*) FROM citizen_requests WHERE id = %s""",
            (cr_id,)).fetchone()[0]
        assert kept == 1


def test_needs_revision_stays_unpublished(monkeypatch):
    _mock_gemini(monkeypatch)
    _mock_geo(monkeypatch)
    with connect() as conn:
        cr_id = _submit(conn)
    thread_id = pipeline.run_pipeline(cr_id)
    out = pipeline.resume_gate(thread_id, "needs_revision", "Test Reviewer")
    assert out["status"] == "needs_revision"
    with connect() as conn:
        # Unpublished and visibly awaiting revision; never in published results.
        pub = conn.execute(
            """SELECT count(*) FROM recommendations r
               JOIN approvals a ON a.recommendation_id = r.id
                AND a.decision = 'approved'
               WHERE r.thread_id = %s""", (thread_id,)).fetchone()[0]
        assert pub == 0
        assert _trace(conn, thread_id)["status"] == "awaiting_approval"


def test_gemini_double_failure_halts_needs_retry_then_operator_retry(monkeypatch):
    """Tasks 7.5 + 7.6: retry-once-then-halt; retry resumes from failed stage."""
    fail = {"n": 2}  # the first attempt AND its single retry fail → halt;
    # the later operator retry then finds the "outage" cleared.
    _mock_gemini(monkeypatch, fail_stage="recommend", fail_count=fail)
    _mock_geo(monkeypatch)
    with connect() as conn:
        cr_id = _submit(conn)
    thread_id = pipeline.run_pipeline(cr_id)

    with connect() as conn:
        t = _trace(conn, thread_id)
        assert t["status"] == "needs_retry"
        errors = [s for s in t["stages"] if s.get("error")]
        assert errors and errors[-1]["stage"] == "Recommend"
        understand_runs = [s for s in t["stages"] if s["stage"] == "Understand"]
        assert len(understand_runs) == 1
        trace_id = t["id"]

    # Operator retry after the outage clears: resumes at Recommend only.
    assert pipeline.retry_run(trace_id) is True
    with connect() as conn:
        t = _trace(conn, thread_id)
        assert t["status"] == "awaiting_approval"
        # Completed upstream stages were NOT re-executed.
        assert len([s for s in t["stages"] if s["stage"] == "Understand"]) == 1
        recommend_entries = [s for s in t["stages"] if s["stage"] == "Recommend"]
        assert len(recommend_entries) == 2  # the failed attempt + the retry
    pipeline.resume_gate(thread_id, "rejected", "Test Reviewer")  # tidy the gate


def test_retry_refused_for_non_halted_run(monkeypatch):
    assert pipeline.retry_run(str(uuid.uuid4())) is False


# --------------------------------------------------------------------------
# Gate consolidation (enhancements task 3.5, design D19)
# --------------------------------------------------------------------------

def _counting_gemini(monkeypatch) -> dict:
    """Mocked Gemini that counts recommendation drafts."""
    calls = {"recommend": 0}

    def fake_live(prompt: str, image_bytes=None) -> str:
        if prompt.startswith("You are drafting ONE"):
            calls["recommend"] += 1
            return RECOMMEND_JSON
        return UNDERSTAND_JSON
    monkeypatch.setattr(gemini, "_live_call", fake_live)
    return calls


def _pending_for_cluster_of(conn, thread_id: str) -> int:
    return conn.execute(
        """SELECT count(*) FROM recommendations r WHERE r.status = 'pending'
             AND r.demand_cluster_id = (SELECT demand_cluster_id FROM recommendations
                                        WHERE thread_id = %s)""",
        (thread_id,)).fetchone()[0]


def test_second_report_joins_pending_draft_without_model_call(monkeypatch):
    calls = _counting_gemini(monkeypatch)
    _mock_geo(monkeypatch)
    with connect() as conn:
        first, second = _submit(conn), _submit(conn)
    t1 = pipeline.run_pipeline(first)
    assert calls["recommend"] == 1
    t2 = pipeline.run_pipeline(second)
    assert calls["recommend"] == 1  # no second draft
    with connect() as conn:
        assert _pending_for_cluster_of(conn, t1) == 1  # one gate item
        trace2 = _trace(conn, t2)
        assert trace2["status"] == "awaiting_approval"
        last = trace2["stages"][-1]
        assert last["stage"] == "Recommend" and last["joined_existing"] is True
        (joined,) = conn.execute(
            "SELECT joined_recommendation_id::text FROM run_traces WHERE thread_id=%s",
            (t2,)).fetchone()
        (rec_id,) = conn.execute(
            "SELECT id::text FROM recommendations WHERE thread_id=%s", (t1,)).fetchone()
        assert joined == rec_id == last["output_ref"]
    assert not pipeline.is_suspended_at_gate(t2)  # the joined run ended cleanly
    pipeline.resume_gate(t1, "rejected", "Test Reviewer")  # tidy the gate


def test_approval_settles_every_joined_run(monkeypatch):
    _counting_gemini(monkeypatch)
    _mock_geo(monkeypatch)
    with connect() as conn:
        crs = [_submit(conn) for _ in range(4)]
    threads = [pipeline.run_pipeline(cr) for cr in crs]
    pipeline.resume_gate(threads[0], "approved", "Test Reviewer")
    with connect() as conn:
        assert [_trace(conn, t)["status"] for t in threads] == ["published"] * 4


def test_report_after_changes_requested_drafts_afresh(monkeypatch):
    calls = _counting_gemini(monkeypatch)
    _mock_geo(monkeypatch)
    with connect() as conn:
        first, later = _submit(conn), _submit(conn)
    t1 = pipeline.run_pipeline(first)
    pipeline.resume_gate(t1, "needs_revision", "Test Reviewer")
    t2 = pipeline.run_pipeline(later)
    assert calls["recommend"] == 2
    with connect() as conn:
        (status,) = conn.execute(
            "SELECT status::text FROM recommendations WHERE thread_id=%s", (t2,)).fetchone()
        assert status == "pending"
    assert pipeline.is_suspended_at_gate(t2)
    pipeline.resume_gate(t2, "rejected", "Test Reviewer")


def test_concurrent_reports_open_one_draft(monkeypatch):
    """Two reports for one existing cluster racing through Recommend."""
    import threading

    from tests.conftest_a import make_cluster
    calls = _counting_gemini(monkeypatch)
    site = offset_point(BASE_LON, BASE_LAT, east_m=10_000 * next(_site))
    _mock_geo(monkeypatch, lonlat=site)
    with connect() as conn:
        make_cluster(conn, lonlat=site, member_embeddings=[[0.03] * 768])
        crs = [_submit(conn) for _ in range(2)]
    threads_out = []
    workers = [threading.Thread(target=lambda c=cr: threads_out.append(
        pipeline.run_pipeline(c))) for cr in crs]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert calls["recommend"] == 1
    with connect() as conn:
        drafts = conn.execute(
            """SELECT count(*) FROM recommendations
               WHERE thread_id = ANY(%s)""", (threads_out,)).fetchone()[0]
        assert drafts == 1
        statuses = sorted(_trace(conn, t)["status"] for t in threads_out)
        assert statuses == ["awaiting_approval", "awaiting_approval"]
    opener = next(t for t in threads_out if pipeline.is_suspended_at_gate(t))
    pipeline.resume_gate(opener, "rejected", "Test Reviewer")
