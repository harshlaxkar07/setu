"""Track A test helpers (imported by the Track A test files).

Deliberately NOT a pytest conftest.py — Track B may need that name. Import
from here: `from tests.conftest_a import ...`.

Tests run inside the backend container against the seeded database. Every row
a test creates uses a submitter_ref with the 'test-' prefix so cleanup can
remove it without disturbing the seeded Region A/B state; cleanup also
recomputes cluster member counts and drops clusters left with no members.
"""
import math
import uuid

import psycopg

from app import db
from app.constants import CATEGORY_WATER, EMBEDDING_DIM

TEST_REF_PREFIX = "test-"

# A test playground far from the seeded Kothrud/Velhe clusters (still lon/lat
# order everywhere: PostGIS points are (lon, lat)).
BASE_LON, BASE_LAT = 74.30, 18.90


def connect() -> psycopg.Connection:
    """Direct test connection (autocommit off; stage code commits itself)."""
    return psycopg.connect(db.DATABASE_URL)


def ensure_pool() -> None:
    """Open the shared app pool for code paths that use db.pool.

    Idempotent: opening an already-open pool is a no-op. Tests never close it
    (closing would break later test files in the same session).
    """
    try:
        db.pool.open()
    except Exception:
        pass  # already open


# ---------------------------------------------------------------- vectors

def unit_vector(axis: int) -> list[float]:
    """768-dim unit vector along one axis."""
    v = [0.0] * EMBEDDING_DIM
    v[axis] = 1.0
    return v


def vector_with_cosine(cos: float, axis_a: int = 0, axis_b: int = 1) -> list[float]:
    """Unit vector whose cosine similarity to unit_vector(axis_a) is `cos`,
    tilted along axis_b — lets tests craft exact similarity scores."""
    v = [0.0] * EMBEDDING_DIM
    v[axis_a] = cos
    v[axis_b] = math.sqrt(max(0.0, 1.0 - cos * cos))
    return v


def offset_point(lon: float, lat: float, east_m: float = 0.0,
                 north_m: float = 0.0) -> tuple[float, float]:
    """(lon, lat) displaced by metres — close enough at Pune's latitude."""
    return (lon + east_m / (111_320.0 * math.cos(math.radians(lat))),
            lat + north_m / 111_320.0)


# ---------------------------------------------------------------- factories

def make_citizen_request(conn, *, channel: str = "text",
                         text: str | None = "test paani nahi aa raha",
                         audio_path: str | None = None,
                         submitter: str | None = None) -> str:
    submitter = submitter or f"{TEST_REF_PREFIX}{uuid.uuid4()}"
    row = conn.execute(
        """INSERT INTO citizen_requests (channel, raw_text, audio_path, submitter_ref)
           VALUES (%s, %s, %s, %s) RETURNING id""",
        (channel, text, audio_path, submitter),
    ).fetchone()
    conn.commit()
    return str(row[0])


def make_structured_request(conn, citizen_request_id: str, *,
                            category: str = CATEGORY_WATER,
                            urgency: str = "high",
                            summary: str = "test water outage summary",
                            language: str = "Hindi",
                            mention: str = "Testpur") -> str:
    row = conn.execute(
        """INSERT INTO structured_requests
             (citizen_request_id, category, urgency, summary,
              detected_language, raw_location_mention)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (citizen_request_id, category, urgency, summary, language, mention),
    ).fetchone()
    conn.commit()
    return str(row[0])


def make_geocoded_request(conn, structured_request_id: str, *,
                          lonlat: tuple[float, float] | None = None,
                          confidence: str = "high",
                          reason: str | None = None,
                          embedding: list[float] | None = None) -> str:
    import json
    lon, lat = lonlat if lonlat else (None, None)
    row = conn.execute(
        """INSERT INTO geocoded_requests
             (structured_request_id, geom, confidence, confidence_reason, embedding)
           VALUES (%s,
                   CASE WHEN %s::float8 IS NULL THEN NULL
                        ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326) END,
                   %s, %s, %s::vector)
           RETURNING id""",
        (structured_request_id, lon, lon, lat, confidence, reason,
         json.dumps(embedding) if embedding is not None else None),
    ).fetchone()
    conn.commit()
    return str(row[0])


def make_request_chain(conn, *, category: str = CATEGORY_WATER,
                       lonlat: tuple[float, float] | None = None,
                       embedding: list[float] | None = None,
                       summary: str = "test water outage summary",
                       confidence: str = "high",
                       reason: str | None = None) -> tuple[str, str, str]:
    """citizen → structured → geocoded rows; returns (cr_id, sr_id, gr_id)."""
    cr = make_citizen_request(conn)
    sr = make_structured_request(conn, cr, category=category, summary=summary)
    gr = make_geocoded_request(conn, sr, lonlat=lonlat, confidence=confidence,
                               reason=reason, embedding=embedding)
    return cr, sr, gr


def make_cluster(conn, *, category: str = CATEGORY_WATER,
                 lonlat: tuple[float, float],
                 summary: str = "test cluster summary",
                 member_embeddings: list[list[float]] = ()) -> str:
    """DemandCluster with one member request per embedding (all at lonlat)."""
    row = conn.execute(
        """INSERT INTO demand_clusters
             (category, centroid, representative_summary, member_count,
              status, confidence)
           VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s,
                   'active', 'high')
           RETURNING id""",
        (category, lonlat[0], lonlat[1], summary, len(member_embeddings)),
    ).fetchone()
    cluster_id = str(row[0])
    for emb in member_embeddings:
        _, _, gr = make_request_chain(conn, category=category, lonlat=lonlat,
                                      embedding=emb)
        conn.execute(
            """INSERT INTO cluster_memberships
                 (geocoded_request_id, demand_cluster_id, similarity_score)
               VALUES (%s, %s, 0.99)""",
            (gr, cluster_id),
        )
    conn.commit()
    return cluster_id


# ----------------------------------------------------------------- cleanup

def _delete_test_trust_flags(conn) -> None:
    conn.execute(
        """DELETE FROM trust_flags WHERE citizen_request_id IN
             (SELECT id FROM citizen_requests WHERE submitter_ref LIKE %s)""",
        (TEST_REF_PREFIX + "%",),
    )


def _delete_memberless_cluster_flags(conn) -> None:
    conn.execute(
        """DELETE FROM trust_flags tf WHERE tf.demand_cluster_id IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM cluster_memberships m
                             WHERE m.demand_cluster_id = tf.demand_cluster_id)""")


def cleanup_test_rows(conn) -> None:
    """Remove every row created by Track A tests and restore seeded state.

    citizen_requests is immutable by trigger; test cleanup transiently
    disables it — the same sanctioned posture the seed script uses.
    """
    conn.execute(
        """DELETE FROM run_traces WHERE citizen_request_id IN
             (SELECT id FROM citizen_requests WHERE submitter_ref LIKE %s)""",
        (TEST_REF_PREFIX + "%",),
    )
    _delete_test_trust_flags(conn)
    conn.execute(
        """DELETE FROM cluster_memberships WHERE geocoded_request_id IN
             (SELECT gr.id FROM geocoded_requests gr
              JOIN structured_requests sr ON sr.id = gr.structured_request_id
              JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
              WHERE cr.submitter_ref LIKE %s)""",
        (TEST_REF_PREFIX + "%",),
    )
    conn.execute(
        """DELETE FROM geocoded_requests WHERE structured_request_id IN
             (SELECT sr.id FROM structured_requests sr
              JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
              WHERE cr.submitter_ref LIKE %s)""",
        (TEST_REF_PREFIX + "%",),
    )
    conn.execute(
        """DELETE FROM structured_requests WHERE citizen_request_id IN
             (SELECT id FROM citizen_requests WHERE submitter_ref LIKE %s)""",
        (TEST_REF_PREFIX + "%",),
    )
    conn.execute(
        """DELETE FROM transcriptions WHERE citizen_request_id IN
             (SELECT id FROM citizen_requests WHERE submitter_ref LIKE %s)""",
        (TEST_REF_PREFIX + "%",),
    )
    conn.execute(
        "ALTER TABLE citizen_requests DISABLE TRIGGER citizen_requests_immutable")
    conn.execute("DELETE FROM citizen_requests WHERE submitter_ref LIKE %s",
                 (TEST_REF_PREFIX + "%",))
    conn.execute(
        "ALTER TABLE citizen_requests ENABLE TRIGGER citizen_requests_immutable")
    # Drop clusters tests founded (now memberless) and restore member counts.
    _delete_memberless_cluster_flags(conn)
    conn.execute(
        """DELETE FROM demand_clusters c
           WHERE NOT EXISTS (SELECT 1 FROM cluster_memberships m
                             WHERE m.demand_cluster_id = c.id)
             AND NOT EXISTS (SELECT 1 FROM priority_indicators p
                             WHERE p.demand_cluster_id = c.id)""")
    conn.execute(
        """UPDATE demand_clusters c SET member_count =
             (SELECT count(*) FROM cluster_memberships m
              WHERE m.demand_cluster_id = c.id)""")
    conn.commit()


def cleanup_test_state() -> None:
    """Purge every 'test-' chain AND any memberless cluster (FK-safe order),
    then restore the seeded cohort's canonical stored scores.

    Shared by the §7 test modules (test_pipeline, test_gate): ad-hoc suspended
    runs, gate decisions, and scoring passes all leave rows that would
    otherwise pollute the category cohort other tests normalize over.
    """
    from app.constants import CATEGORY_WATER
    from app.stages import fuse as fuse_stage
    from app.stages import score as score_stage

    with connect() as conn:
        conn.execute("""
            DELETE FROM cluster_memberships WHERE geocoded_request_id IN (
              SELECT gr.id FROM geocoded_requests gr
              JOIN structured_requests sr ON sr.id = gr.structured_request_id
              JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
              WHERE cr.submitter_ref LIKE 'test-%')""")
        _delete_test_trust_flags(conn)
        _delete_memberless_cluster_flags(conn)
        # Any cluster left without members (from this or any prior ad-hoc run)
        # goes away entirely, children first.
        for tbl in ("approvals",):
            conn.execute("""
                DELETE FROM approvals WHERE recommendation_id IN (
                  SELECT r.id FROM recommendations r
                  WHERE NOT EXISTS (SELECT 1 FROM cluster_memberships cm
                                    WHERE cm.demand_cluster_id = r.demand_cluster_id))""")
        for tbl in ("recommendations", "verification_records", "priority_scores",
                    "priority_indicators", "gap_scores"):
            conn.execute(f"""
                DELETE FROM {tbl} WHERE demand_cluster_id IN (
                  SELECT dc.id FROM demand_clusters dc
                  WHERE NOT EXISTS (SELECT 1 FROM cluster_memberships cm
                                    WHERE cm.demand_cluster_id = dc.id))""")
        conn.execute("""
            DELETE FROM demand_clusters dc
            WHERE NOT EXISTS (SELECT 1 FROM cluster_memberships cm
                              WHERE cm.demand_cluster_id = dc.id)""")
        conn.execute("""
            DELETE FROM run_traces WHERE citizen_request_id IN
              (SELECT id FROM citizen_requests WHERE submitter_ref LIKE 'test-%')""")
        conn.execute("""
            DELETE FROM geocoded_requests WHERE structured_request_id IN (
              SELECT sr.id FROM structured_requests sr
              JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
              WHERE cr.submitter_ref LIKE 'test-%')""")
        conn.execute("""
            DELETE FROM structured_requests WHERE citizen_request_id IN
              (SELECT id FROM citizen_requests WHERE submitter_ref LIKE 'test-%')""")
        conn.execute("""
            DELETE FROM transcriptions WHERE citizen_request_id IN
              (SELECT id FROM citizen_requests WHERE submitter_ref LIKE 'test-%')""")
        conn.execute(
            "ALTER TABLE citizen_requests DISABLE TRIGGER citizen_requests_immutable")
        conn.execute(
            "DELETE FROM citizen_requests WHERE submitter_ref LIKE 'test-%'")
        conn.execute(
            "ALTER TABLE citizen_requests ENABLE TRIGGER citizen_requests_immutable")
        # Member counts must match memberships again before re-scoring, or the
        # volume indicator would be computed from a stale total.
        conn.execute(
            """UPDATE demand_clusters c SET member_count =
                 (SELECT count(*) FROM cluster_memberships m
                  WHERE m.demand_cluster_id = c.id)""")
        conn.commit()
        for (cid,) in conn.execute(
            "SELECT id::text FROM demand_clusters WHERE category = %s",
            (CATEGORY_WATER,),
        ).fetchall():
            fuse_stage.fuse_cluster(conn, cid)
        score_stage.score_category(conn, CATEGORY_WATER)
        conn.commit()


# --------------------------------------------------------- reviewer auth

def reviewer_headers() -> dict[str, str]:
    """Authorization header for the first configured reviewer (REVIEWERS in
    .env). The token is signed with the same SESSION_SECRET the running
    backend uses, so it works for in-process and live-server calls alike."""
    import pytest

    from app import auth
    names = sorted(auth.reviewers())
    if not names:
        pytest.fail("REVIEWERS is not configured in .env — decision endpoints "
                    "require a reviewer account (see README)")
    token, _ = auth.issue_token(names[0])
    return {"Authorization": f"Bearer {token}"}


def reviewer_name() -> str:
    from app import auth
    return sorted(auth.reviewers())[0]
