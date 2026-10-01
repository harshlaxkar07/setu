"""Trust & anti-manipulation rules (enhancements tasks 3.1–3.2, design D2).

Each test builds its own cluster in the test playground (far from the seeded
regions) with explicit request timestamps, so windows are exercised exactly.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.constants import (
    CATEGORY_WATER,
    TRUST_BURST_MIN_MATCHES,
    TRUST_REPEAT_LIMIT,
    TRUST_SPIKE_MIN_ARRIVALS,
)
from app.stages import fuse, score, trust
from tests.conftest_a import (
    reviewer_headers,
    reviewer_name,
    BASE_LAT,
    BASE_LON,
    TEST_REF_PREFIX,
    cleanup_test_rows,
    connect,
    unit_vector,
    vector_with_cosine,
)

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def conn():
    c = connect()
    yield c
    cleanup_test_rows(c)
    c.close()


def _cluster(conn, lonlat=(BASE_LON, BASE_LAT)) -> str:
    (cid,) = conn.execute(
        """INSERT INTO demand_clusters (category, centroid, representative_summary,
                                        member_count, status, confidence)
           VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), 'test trust cluster',
                   0, 'active', 'high') RETURNING id""",
        (CATEGORY_WATER, *lonlat)).fetchone()
    conn.commit()
    return str(cid)


def _member(conn, cluster_id, *, text, at, submitter=None, embedding=None,
            joined_at=None) -> tuple[str, str]:
    """A full request chain created at `at`, joined to the cluster. Returns
    (citizen_request_id, geocoded_request_id)."""
    submitter = submitter or f"{TEST_REF_PREFIX}{uuid.uuid4()}"
    (cr,) = conn.execute(
        """INSERT INTO citizen_requests (channel, raw_text, submitter_ref, created_at)
           VALUES ('text', %s, %s, %s) RETURNING id""", (text, submitter, at)).fetchone()
    (sr,) = conn.execute(
        """INSERT INTO structured_requests (citizen_request_id, category, urgency,
               summary, detected_language, raw_location_mention)
           VALUES (%s, %s, 'high', 'test', 'Hindi', 'Testpur') RETURNING id""",
        (cr, CATEGORY_WATER)).fetchone()
    (gr,) = conn.execute(
        """INSERT INTO geocoded_requests (structured_request_id, geom, confidence, embedding)
           VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), 'high', %s::vector)
           RETURNING id""",
        (sr, BASE_LON, BASE_LAT,
         json.dumps(embedding or unit_vector(uuid.uuid4().int % 700)))).fetchone()
    conn.execute(
        """INSERT INTO cluster_memberships (geocoded_request_id, demand_cluster_id,
                                            similarity_score, created_at)
           VALUES (%s, %s, 0.9, %s)""", (gr, cluster_id, joined_at or at))
    conn.execute("UPDATE demand_clusters SET member_count = member_count + 1 WHERE id = %s",
                 (cluster_id,))
    conn.commit()
    return str(cr), str(gr)


def _flags(conn, cr):
    return {r[0]: r[1] for r in conn.execute(
        "SELECT rule, reason FROM trust_flags WHERE citizen_request_id = %s", (cr,))}


# --------------------------------------------------------- duplicate burst

def test_burst_of_near_identical_texts_is_flagged(conn):
    cid = _cluster(conn)
    text = "Testpur में कई हफ़्तों से पीने का पानी नहीं आ रहा"
    results = []
    for i in range(TRUST_BURST_MIN_MATCHES + 3):
        cr, gr = _member(conn, cid, text=text + ("!" if i % 2 else ""),
                         at=NOW - timedelta(minutes=8) + timedelta(seconds=20 * i))
        results.append((cr, trust.run(conn, gr, cid)))
    flagged = [cr for cr, flags in results if any(f["rule"] == "duplicate_burst" for f in flags)]
    # Requests up to the threshold are not flagged; every one after it is.
    assert flagged == [cr for cr, _ in results[TRUST_BURST_MIN_MATCHES:]]
    reason = _flags(conn, flagged[-1])["duplicate_burst"]
    assert "near-identical requests" in reason and str(TRUST_BURST_MIN_MATCHES + 2) in reason
    # Flag, never delete: every request is still stored and still a member.
    (members,) = conn.execute(
        "SELECT count(*) FROM cluster_memberships WHERE demand_cluster_id = %s",
        (cid,)).fetchone()
    assert members == TRUST_BURST_MIN_MATCHES + 3


def test_embedding_near_duplicates_count_even_with_different_wording(conn):
    cid = _cluster(conn)
    last = None
    for i in range(TRUST_BURST_MIN_MATCHES + 1):
        vec = vector_with_cosine(0.99 if i else 1.0)
        cr, gr = _member(conn, cid, text=f"variant wording number {i}",
                         at=NOW - timedelta(minutes=5) + timedelta(seconds=i), embedding=vec)
        last = (cr, trust.run(conn, gr, cid))
    assert any(f["rule"] == "duplicate_burst" for f in last[1])


def test_similar_complaints_spread_over_days_are_not_flagged(conn):
    """The spec's negative case: 5 similar complaints over 5 days."""
    cid = _cluster(conn)
    for day in range(5):
        cr, gr = _member(conn, cid, text="Testpur me paani nahi aa raha",
                         at=NOW - timedelta(days=5 - day))
        assert not any(f["rule"] == "duplicate_burst" for f in trust.run(conn, gr, cid))


# ------------------------------------------------------------ repeat source

def test_one_source_flooding_a_cluster_is_flagged(conn):
    cid = _cluster(conn)
    who = f"{TEST_REF_PREFIX}flooder-{uuid.uuid4()}"
    results = []
    for i in range(12):
        cr, gr = _member(conn, cid, text=f"different complaint {i} {uuid.uuid4()}",
                         at=NOW - timedelta(minutes=50) + timedelta(minutes=4 * i),
                         submitter=who)
        results.append((cr, trust.run(conn, gr, cid)))
    flagged = [cr for cr, flags in results if any(f["rule"] == "repeat_source" for f in flags)]
    assert flagged == [cr for cr, _ in results[TRUST_REPEAT_LIMIT:]]
    assert _flags(conn, results[-1][0])["repeat_source"] == \
        "repeat source: 12 submissions in 1 hour from one source"


def test_distinct_sources_are_not_repeat_flagged(conn):
    cid = _cluster(conn)
    for i in range(6):
        cr, gr = _member(conn, cid, text=f"complaint {uuid.uuid4()}",
                         at=NOW - timedelta(minutes=30) + timedelta(minutes=i))
        assert not any(f["rule"] == "repeat_source" for f in trust.run(conn, gr, cid))


# ------------------------------------------------------------ cluster spike

def test_spike_over_baseline_lowers_cluster_confidence(conn):
    """~2 members/day for 10 days, then a burst in the last hour."""
    cid = _cluster(conn)
    for i in range(20):
        at = NOW - timedelta(days=10) + timedelta(hours=12 * i)
        _member(conn, cid, text=f"history {uuid.uuid4()}", at=at)
    flags = []
    for i in range(TRUST_SPIKE_MIN_ARRIVALS + 5):
        cr, gr = _member(conn, cid, text=f"spike {uuid.uuid4()}",
                         at=NOW - timedelta(minutes=30) + timedelta(seconds=30 * i))
        flags += trust.run(conn, gr, cid)
    spikes = [f for f in flags if f["rule"] == "cluster_spike"]
    assert len(spikes) == 1  # one open cluster flag, not one per request
    confidence, reason = conn.execute(
        "SELECT confidence, confidence_reason FROM demand_clusters WHERE id = %s",
        (cid,)).fetchone()
    assert confidence == "medium"
    assert "cluster spike" in reason and "baseline" in reason


def test_steady_cluster_is_not_spike_flagged(conn):
    cid = _cluster(conn)
    for i in range(30):
        cr, gr = _member(conn, cid, text=f"steady {uuid.uuid4()}",
                         at=NOW - timedelta(days=29) + timedelta(days=i))
        assert not any(f["rule"] == "cluster_spike" for f in trust.run(conn, gr, cid))
    (confidence,) = conn.execute(
        "SELECT confidence FROM demand_clusters WHERE id = %s", (cid,)).fetchone()
    assert confidence == "high"


# ------------------------------------------- volume exclusion (task 3.2)

def _score(conn, cid) -> float:
    fuse.fuse_cluster(conn, cid)
    score.score_category(conn, CATEGORY_WATER)
    conn.commit()
    return float(conn.execute(
        "SELECT score FROM priority_scores WHERE demand_cluster_id = %s",
        (cid,)).fetchone()[0])


def test_flagged_requests_leave_the_priority_score_unchanged(conn):
    """Score with only unflagged members, then inject 10 requests that ARE
    flagged: the score is identical, the member count shows the total, and
    the volume indicator states the exclusion (never silent)."""
    from tests.conftest_a import cleanup_test_state
    try:
        cid = _cluster(conn)
        for i in range(3):
            _member(conn, cid, text=f"genuine {uuid.uuid4()}",
                    at=NOW - timedelta(days=3 - i))
        spam = "Testpur spam spam paani nahi"
        # The first TRUST_BURST_MIN_MATCHES copies are below the threshold.
        for i in range(TRUST_BURST_MIN_MATCHES):
            _, gr = _member(conn, cid, text=spam, at=NOW - timedelta(seconds=400 - i))
            assert trust.run(conn, gr, cid) == []
        before = _score(conn, cid)

        for i in range(10):
            _, gr = _member(conn, cid, text=spam, at=NOW - timedelta(seconds=200 - i))
            assert [f["rule"] for f in trust.run(conn, gr, cid)] == ["duplicate_burst"]
        after = _score(conn, cid)

        assert after == before
        total = conn.execute("SELECT member_count FROM demand_clusters WHERE id=%s",
                             (cid,)).fetchone()[0]
        assert total == 3 + TRUST_BURST_MIN_MATCHES + 10
        assert trust.counted_volume(conn, cid) == 3 + TRUST_BURST_MIN_MATCHES
        value_text, value, citations = conn.execute(
            """SELECT value_text, value_numeric, source_citations FROM priority_indicators
               WHERE demand_cluster_id = %s AND name = 'complaint volume'""",
            (cid,)).fetchone()
        assert float(value) == 3 + TRUST_BURST_MIN_MATCHES
        assert "10 more excluded as suspected manipulation" in value_text
        assert citations[0]["member_count"] == total
        assert citations[0]["excluded_by_trust_flags"] == 10
    finally:
        cleanup_test_rows(conn)
        cleanup_test_state()  # restore the seeded water cohort's stored scores


def test_cleared_flag_restores_the_request_to_counted_volume(conn):
    cid = _cluster(conn)
    who = f"{TEST_REF_PREFIX}flooder-{uuid.uuid4()}"
    crs = [_member(conn, cid, text=f"c {uuid.uuid4()}", submitter=who,
                   at=NOW - timedelta(minutes=10 - i))[0] for i in range(TRUST_REPEAT_LIMIT + 1)]
    gr = conn.execute(
        """SELECT gr.id FROM geocoded_requests gr JOIN structured_requests sr
             ON sr.id = gr.structured_request_id WHERE sr.citizen_request_id = %s""",
        (crs[-1],)).fetchone()[0]
    trust.run(conn, str(gr), cid)
    assert trust.counted_volume(conn, cid) == TRUST_REPEAT_LIMIT
    conn.execute("""UPDATE trust_flags SET status = 'cleared', reviewer = 'tester',
                    reviewed_at = now() WHERE citizen_request_id = %s""", (crs[-1],))
    conn.commit()
    assert trust.counted_volume(conn, cid) == TRUST_REPEAT_LIMIT + 1


# ----------------------------------------------- review API (task 3.3)

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest_a import ensure_pool
    ensure_pool()
    return TestClient(app)


def _repeat_flagged_cluster(conn) -> tuple[str, str]:
    """A cluster whose last request carries an open repeat_source flag."""
    cid = _cluster(conn)
    who = f"{TEST_REF_PREFIX}flooder-{uuid.uuid4()}"
    gr = None
    for i in range(TRUST_REPEAT_LIMIT + 1):
        _, gr = _member(conn, cid, text=f"c {uuid.uuid4()}", submitter=who,
                        at=NOW - timedelta(minutes=10 - i))
    trust.run(conn, gr, cid)
    (flag_id,) = conn.execute(
        "SELECT id::text FROM trust_flags WHERE demand_cluster_id = %s", (cid,)).fetchone()
    return cid, flag_id


def test_cluster_api_reports_counted_volume(conn, client):
    cid, _ = _repeat_flagged_cluster(conn)
    body = next(c for c in client.get("/api/clusters").json() if c["id"] == cid)
    assert body["member_count"] == TRUST_REPEAT_LIMIT + 1
    assert body["counted_volume"] == TRUST_REPEAT_LIMIT
    assert body["trust"] == {"excluded": 1, "open_request_flags": 1,
                             "open_cluster_flags": 0}


def test_clearing_a_flag_restores_volume_and_records_reviewer(conn, client):
    from tests.conftest_a import cleanup_test_state
    try:
        cid, flag_id = _repeat_flagged_cluster(conn)
        listed = client.get("/api/trust/flags", params={"cluster_id": cid}).json()
        assert [f["id"] for f in listed] == [flag_id]
        r = client.post(f"/api/trust/flags/{flag_id}/review", headers=reviewer_headers(),
                        json={"decision": "clear", "reviewer": "Test Reviewer"})
        assert r.status_code == 200 and r.json()["status"] == "cleared"
        status, reviewer, reviewed_at = conn.execute(
            "SELECT status, reviewer, reviewed_at FROM trust_flags WHERE id = %s",
            (flag_id,)).fetchone()
        # Identity comes from the sign-in token, not the body (D15).
        assert (status, reviewer) == ("cleared", reviewer_name()) and reviewed_at
        # Re-scored in the same transaction: the cleared request counts again.
        (value,) = conn.execute(
            """SELECT value_numeric FROM priority_indicators
               WHERE demand_cluster_id = %s AND name = 'complaint volume'""",
            (cid,)).fetchone()
        assert float(value) == TRUST_REPEAT_LIMIT + 1
        # A second review of the same flag is refused, not silently re-applied.
        again = client.post(f"/api/trust/flags/{flag_id}/review", headers=reviewer_headers(),
                            json={"decision": "confirm", "reviewer": "Someone"})
        assert again.status_code == 409
    finally:
        cleanup_test_rows(conn)
        cleanup_test_state()


def test_unknown_flag_is_404(client):
    r = client.post(f"/api/trust/flags/{uuid.uuid4()}/review", headers=reviewer_headers(),
                    json={"decision": "clear", "reviewer": "x"})
    assert r.status_code == 404


def test_trust_review_requires_sign_in(conn, client):
    _, flag_id = _repeat_flagged_cluster(conn)
    r = client.post(f"/api/trust/flags/{flag_id}/review", json={"decision": "clear"})
    assert r.status_code == 401
    (status,) = conn.execute("SELECT status FROM trust_flags WHERE id = %s",
                             (flag_id,)).fetchone()
    assert status == "open"
