"""Score stage tests (tasks 5.3–5.4) — run inside the backend container:

    docker compose exec -T backend pytest tests/test_score.py -q

Write-tests run in rolled-back transactions; the seeded demo state survives.
"""
import os
import uuid

import psycopg
import pytest

from app.constants import (
    CATEGORY_WATER,
    DEGENERATE_NORM,
    INVESTMENT_DEFICIT,
    WEIGHT_GAP,
    WEIGHT_INVESTMENT_DEFICIT,
    WEIGHT_VOLUME,
)
from app.stages.fuse import fuse_cluster
from app.stages.score import (
    OWNED_INDICATORS,
    minmax_normalize,
    score_category,
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://setu:setu_local_dev@localhost:5434/setu"
)


@pytest.fixture()
def conn():
    with psycopg.connect(DATABASE_URL) as c:
        yield c
        c.rollback()


def _clusters(conn, category: str) -> list[tuple[str, int]]:
    return [
        (str(r[0]), r[1])
        for r in conn.execute(
            "SELECT id, member_count FROM demand_clusters WHERE category = %s "
            "ORDER BY member_count DESC",
            (category,),
        ).fetchall()
    ]


def _score_row(conn, cluster_id: str) -> dict:
    r = conn.execute(
        """SELECT score, gap_norm, investment_deficit_norm, volume_norm, weights
           FROM priority_scores WHERE demand_cluster_id = %s
           ORDER BY created_at DESC LIMIT 1""",
        (cluster_id,),
    ).fetchone()
    assert r is not None
    return {
        "score": float(r[0]), "gap_norm": float(r[1]),
        "investment_deficit_norm": float(r[2]), "volume_norm": float(r[3]),
        "weights": r[4],
    }


def _indicators(conn, cluster_id: str) -> dict[str, tuple]:
    return {
        r[0]: (r[1], float(r[2]) if r[2] is not None else None, r[3])
        for r in conn.execute(
            """SELECT name, value_text, value_numeric, source_citations
               FROM priority_indicators WHERE demand_cluster_id = %s""",
            (cluster_id,),
        ).fetchall()
    }


# --------------------------------------------------------------------------
# Normalization mechanics
# --------------------------------------------------------------------------

def test_minmax_normalize_spans_zero_to_one():
    norms = minmax_normalize({"a": 10.0, "b": 20.0, "c": 15.0})
    assert norms == {"a": 0.0, "b": 1.0, "c": 0.5}


def test_minmax_degenerate_is_the_defined_constant():
    """All-equal raw values → DEGENERATE_NORM, never NaN or an error."""
    norms = minmax_normalize({"a": 7.0, "b": 7.0})
    assert norms == {"a": DEGENERATE_NORM, "b": DEGENERATE_NORM}
    assert minmax_normalize({"only": 3.0}) == {"only": DEGENERATE_NORM}


# --------------------------------------------------------------------------
# Requirement: PriorityIndicators are named, valued, individually recorded
# --------------------------------------------------------------------------

def test_score_writes_all_named_indicators_with_citations(conn):
    """Every cluster gets the four named factors, each cited (task 5.3)."""
    for cid, _ in _clusters(conn, CATEGORY_WATER):
        fuse_cluster(conn, cid)
    score_category(conn, CATEGORY_WATER)

    for cid, _ in _clusters(conn, CATEGORY_WATER):
        inds = _indicators(conn, cid)
        for name in OWNED_INDICATORS:
            assert name in inds, f"missing indicator {name!r}"
            value_text, value_numeric, citations = inds[name]
            assert value_text or value_numeric is not None
            assert isinstance(citations, list) and len(citations) > 0

        # Individually retrievable: one row fetchable by (cluster, name) alone.
        row = conn.execute(
            """SELECT value_text FROM priority_indicators
               WHERE demand_cluster_id = %s AND name = 'historical investment'""",
            (cid,),
        ).fetchone()
        assert row is not None


def test_preexisting_indicators_survive_rescoring(conn):
    """The seeded under-representation signal is kept across a re-score."""
    clusters = _clusters(conn, CATEGORY_WATER)
    region_b = clusters[-1][0]  # smallest member count = Velhe
    before = conn.execute(
        """SELECT count(*) FROM priority_indicators
           WHERE demand_cluster_id = %s
             AND name = 'possible under-representation signal'""",
        (region_b,),
    ).fetchone()[0]
    assert before == 1, "seeded under-representation indicator expected"

    for cid, _ in clusters:
        fuse_cluster(conn, cid)
    score_category(conn, CATEGORY_WATER)

    after = conn.execute(
        """SELECT count(*) FROM priority_indicators
           WHERE demand_cluster_id = %s
             AND name = 'possible under-representation signal'""",
        (region_b,),
    ).fetchone()[0]
    assert after == 1


# --------------------------------------------------------------------------
# Requirement: composite score uses the locked formula and stored components
# --------------------------------------------------------------------------

def test_score_formula_and_weights_are_the_locked_constants(conn):
    """score == 0.5·gap + 0.3·investment + 0.2·volume from stored components."""
    for cid, _ in _clusters(conn, CATEGORY_WATER):
        fuse_cluster(conn, cid)
    score_category(conn, CATEGORY_WATER)

    for cid, _ in _clusters(conn, CATEGORY_WATER):
        s = _score_row(conn, cid)
        assert s["weights"] == {
            "gap": WEIGHT_GAP,
            "investment_deficit": WEIGHT_INVESTMENT_DEFICIT,
            "volume": WEIGHT_VOLUME,
        }
        expected = (
            WEIGHT_GAP * s["gap_norm"]
            + WEIGHT_INVESTMENT_DEFICIT * s["investment_deficit_norm"]
            + WEIGHT_VOLUME * s["volume_norm"]
        )
        assert abs(s["score"] - expected) < 1e-9
        for term in ("gap_norm", "investment_deficit_norm", "volume_norm"):
            assert 0.0 <= s[term] <= 1.0


def test_investment_mapping_low_beats_high(conn):
    """low→1.0 / high→0.0 deficit mapping lands in the stored indicator."""
    for cid, _ in _clusters(conn, CATEGORY_WATER):
        fuse_cluster(conn, cid)
    score_category(conn, CATEGORY_WATER)

    clusters = _clusters(conn, CATEGORY_WATER)
    region_a, region_b = clusters[0][0], clusters[-1][0]
    inv_a = _indicators(conn, region_a)["historical investment"]
    inv_b = _indicators(conn, region_b)["historical investment"]
    assert inv_a[0] == "high" and inv_a[1] == INVESTMENT_DEFICIT["high"]
    assert inv_b[0] == "low" and inv_b[1] == INVESTMENT_DEFICIT["low"]


def test_degenerate_same_investment_category(conn):
    """A category where every cluster shares the investment label scores with
    investment_deficit_norm == DEGENERATE_NORM for all (spec scenario)."""
    category = f"test_degenerate_{uuid.uuid4().hex[:8]}"
    # Two synthetic clusters near the seeded Region A centroid — both match the
    # same nearest region profile, hence the same investment label.
    lat, lon = conn.execute(
        """SELECT ST_Y(centroid), ST_X(centroid) FROM demand_clusters
           WHERE category = %s ORDER BY member_count DESC LIMIT 1""",
        (CATEGORY_WATER,),
    ).fetchone()
    ids = []
    for i, members in enumerate((40, 7)):
        row = conn.execute(
            """INSERT INTO demand_clusters
                 (category, centroid, representative_summary, member_count)
               VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)
               RETURNING id""",
            (category, lon + i * 0.001, lat, "degenerate-test cluster", members),
        ).fetchone()
        ids.append(str(row[0]))
        fuse_cluster(conn, ids[-1])

    score_category(conn, category)

    norms = {cid: _score_row(conn, cid) for cid in ids}
    for cid in ids:
        assert norms[cid]["investment_deficit_norm"] == DEGENERATE_NORM
    # Volume still differentiates within the synthetic pair.
    assert norms[ids[0]]["volume_norm"] == 1.0
    assert norms[ids[1]]["volume_norm"] == 0.0


def test_score_unfused_category_raises(conn):
    """Scoring a category holding an unfused cluster is a loud ordering error."""
    category = f"test_unfused_{uuid.uuid4().hex[:8]}"
    conn.execute(
        """INSERT INTO demand_clusters
             (category, centroid, representative_summary, member_count)
           VALUES (%s, ST_SetSRID(ST_MakePoint(73.8, 18.5), 4326), 'x', 3)""",
        (category,),
    )
    with pytest.raises(ValueError, match="not yet fused"):
        score_category(conn, category)
