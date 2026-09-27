"""Recommend stage tests (task 5.7) — run inside the backend container:

    docker compose exec -T backend pytest tests/test_recommend.py -q

Gemini is ALWAYS mocked here via call_gemini's `_caller` injection point —
no live LLM traffic. Write-tests run in rolled-back transactions.
"""
import json
import os

import psycopg
import pytest

from app.constants import CATEGORY_WATER
from app.stages import recommend
from app.stages.recommend import RecommendationRejected

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://setu:setu_local_dev@localhost:5434/setu"
)


@pytest.fixture()
def conn():
    with psycopg.connect(DATABASE_URL) as c:
        yield c
        c.rollback()


@pytest.fixture()
def region_b(conn) -> str:
    """The seeded Region B (Velhe) cluster id — smallest water cluster."""
    row = conn.execute(
        """SELECT id FROM demand_clusters WHERE category = %s
           ORDER BY member_count ASC LIMIT 1""",
        (CATEGORY_WATER,),
    ).fetchone()
    assert row is not None, "seeded demo database required"
    return str(row[0])


def _mock_caller(payload: dict):
    """A fake Gemini live-call returning a fixed JSON body."""
    def caller(prompt: str, image_bytes=None) -> str:
        assert "priority indicators" in prompt.lower()
        return json.dumps(payload)
    return caller


VALID_DRAFT = {
    "intervention_text": (
        "Commission two community water points with piped distribution in the "
        "village, prioritized for the next capital works cycle; interim tanker "
        "supply until commissioning."
    ),
    "intervention_type": "new_infrastructure",
    "cited_indicators": [
        "distance to nearest functioning source",
        "historical investment",
    ],
}


# --------------------------------------------------------------------------
# Happy path: cited draft lands as status 'pending' with citations
# --------------------------------------------------------------------------

def test_cited_draft_is_stored_pending(conn, region_b):
    rec_id = recommend.run(conn, region_b, _caller=_mock_caller(VALID_DRAFT))

    row = conn.execute(
        """SELECT demand_cluster_id::text, intervention_text, intervention_type,
                  indicator_citations, status::text, thread_id
           FROM recommendations WHERE id = %s""",
        (rec_id,),
    ).fetchone()
    assert row is not None
    cluster_id, text, itype, citations, status, thread_id = row

    # Cluster citation: the NOT NULL FK back to the DemandCluster it addresses.
    assert cluster_id == region_b
    assert text == VALID_DRAFT["intervention_text"]
    assert itype == "new_infrastructure"
    # Indicator citations: non-empty, resolving to real indicator rows.
    assert isinstance(citations, list) and len(citations) == 2
    names = {c["name"] for c in citations}
    assert names == {"distance to nearest functioning source",
                     "historical investment"}
    for c in citations:
        exists = conn.execute(
            "SELECT 1 FROM priority_indicators WHERE id = %s AND demand_cluster_id = %s",
            (c["indicator_id"], region_b),
        ).fetchone()
        assert exists is not None
    # Draft (unpublished) status; publication is the gate's job (§7).
    assert status == "pending"
    assert thread_id is None


def test_thread_id_passthrough_for_orchestrator(conn, region_b):
    """§7 hands the LangGraph thread id through; it lands on the row."""
    rec_id = recommend.run(
        conn, region_b, thread_id="thread-test-123",
        _caller=_mock_caller(VALID_DRAFT),
    )
    row = conn.execute(
        "SELECT thread_id FROM recommendations WHERE id = %s", (rec_id,)
    ).fetchone()
    assert row[0] == "thread-test-123"


# --------------------------------------------------------------------------
# Rejection paths: uncited or malformed output is never stored
# --------------------------------------------------------------------------

def _recommendation_count(conn, cluster_id: str) -> int:
    return conn.execute(
        "SELECT count(*) FROM recommendations WHERE demand_cluster_id = %s",
        (cluster_id,),
    ).fetchone()[0]


def test_empty_citations_rejected_not_stored(conn, region_b):
    """Output with no cited indicators → RecommendationRejected, no row."""
    before = _recommendation_count(conn, region_b)
    uncited = dict(VALID_DRAFT, cited_indicators=[])
    with pytest.raises(RecommendationRejected):
        recommend.run(conn, region_b, _caller=_mock_caller(uncited))
    assert _recommendation_count(conn, region_b) == before


def test_unresolvable_citations_rejected_not_stored(conn, region_b):
    """Citations naming indicators the cluster does not have → rejected."""
    before = _recommendation_count(conn, region_b)
    bogus = dict(VALID_DRAFT, cited_indicators=["made-up factor", "another fake"])
    with pytest.raises(RecommendationRejected):
        recommend.run(conn, region_b, _caller=_mock_caller(bogus))
    assert _recommendation_count(conn, region_b) == before


def test_malformed_output_fails_schema_validation(conn, region_b):
    """Structurally malformed output fails call_gemini's schema binding —
    the stage contract fails rather than passing garbage downstream."""
    before = _recommendation_count(conn, region_b)
    with pytest.raises(Exception, match="schema-bound output invalid"):
        recommend.run(
            conn, region_b,
            _caller=_mock_caller({"totally": "wrong shape"}),
        )
    assert _recommendation_count(conn, region_b) == before


def test_recommend_requires_scored_cluster(conn):
    """A cluster with no PriorityScore cannot be recommended against."""
    row = conn.execute(
        """INSERT INTO demand_clusters
             (category, centroid, representative_summary, member_count)
           VALUES ('water_infrastructure',
                   ST_SetSRID(ST_MakePoint(73.9, 18.4), 4326), 'unscored', 1)
           RETURNING id"""
    ).fetchone()
    with pytest.raises(ValueError, match="no PriorityScore"):
        recommend.run(conn, str(row[0]), _caller=_mock_caller(VALID_DRAFT))
