"""Hash-chained decision log (enhancements task 4.3, design D14)."""
import threading
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import audit, db, pipeline
from app.main import app
from tests.conftest_a import cleanup_test_state, connect, ensure_pool, reviewer_name
from tests.test_pipeline import _mock_geo, _submit, _counting_gemini


@pytest.fixture(autouse=True, scope="module")
def _restore():
    ensure_pool()
    yield
    cleanup_test_state()


def _append(conn, n=1):
    for i in range(n):
        audit.append(conn, kind="test", subject_id=str(uuid.uuid4()),
                     decision="approved", reviewer="Tester", payload={"i": i})
    conn.commit()


def test_chain_verifies_intact_via_api():
    with connect() as conn:
        _append(conn, 3)
    body = TestClient(app).get("/api/audit/verify").json()
    assert body["intact"] is True and body["first_break"] is None
    assert body["entries"] >= 3


def test_tampered_entry_is_reported_as_first_break():
    with connect() as conn:
        _append(conn, 3)
        seq, reviewer = conn.execute(
            "SELECT seq, reviewer FROM decision_log ORDER BY seq DESC OFFSET 1 LIMIT 1"
        ).fetchone()
        # Tamper directly in the database, bypassing the append-only trigger
        # as an attacker with DB access would.
        conn.execute("ALTER TABLE decision_log DISABLE TRIGGER decision_log_append_only")
        conn.execute("UPDATE decision_log SET reviewer = 'Mallory' WHERE seq = %s", (seq,))
        conn.commit()
        try:
            result = audit.verify(conn)
            assert result["intact"] is False
            assert result["first_break"]["seq"] == seq
            assert "edited" in result["first_break"]["reason"]
        finally:
            conn.execute("UPDATE decision_log SET reviewer = %s WHERE seq = %s",
                         (reviewer, seq))
            conn.execute("ALTER TABLE decision_log ENABLE TRIGGER decision_log_append_only")
            conn.commit()
        assert audit.verify(conn)["intact"] is True


def test_log_is_append_only_in_normal_operation():
    with connect() as conn:
        _append(conn)
        with pytest.raises(psycopg.Error):
            conn.execute("DELETE FROM decision_log WHERE seq = "
                         "(SELECT max(seq) FROM decision_log)")
        conn.rollback()


def test_gate_decision_is_logged_with_the_reviewer(monkeypatch):
    _counting_gemini(monkeypatch)
    _mock_geo(monkeypatch)
    with connect() as conn:
        cr = _submit(conn)
    thread = pipeline.run_pipeline(cr)
    pipeline.resume_gate(thread, "approved", reviewer_name())
    with connect() as conn:
        kind, decision, reviewer = conn.execute(
            """SELECT kind, decision, reviewer FROM decision_log
               ORDER BY seq DESC LIMIT 1""").fetchone()
    assert (kind, decision, reviewer) == ("publish_gate", "approved", reviewer_name())


def test_parallel_approvals_leave_an_intact_chain(monkeypatch):
    """Concurrent decisions serialise into one linear chain."""
    _counting_gemini(monkeypatch)
    threads = []
    for _ in range(4):
        _mock_geo(monkeypatch)  # a fresh site each: four separate gate items
        with connect() as conn:
            threads.append(pipeline.run_pipeline(_submit(conn)))
    workers = [threading.Thread(target=pipeline.resume_gate,
                                args=(t, "approved", reviewer_name())) for t in threads]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    with connect() as conn:
        result = audit.verify(conn)
        (n,) = conn.execute(
            "SELECT count(*) FROM decision_log WHERE payload->>'thread_id' = ANY(%s)",
            (threads,)).fetchone()
    assert n == 4
    assert result["intact"] is True
