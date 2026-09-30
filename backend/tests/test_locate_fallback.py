"""Informal-location fallbacks (enhancements task 2.4, design D8).

Runs against the seeded database (regions carry aliases, facilities carry
names). Nominatim is never called live: transports are injected.
"""
import json

import pytest

from app import gemini as gemini_mod
from app.stages import cluster as cluster_stage
from app.stages import locate
from tests.conftest_a import cleanup_test_rows, connect
from tests.test_locate import make_sr, nominatim_result


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(locate, "MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(locate, "FIXTURE_DIR", tmp_path)
    monkeypatch.setattr(gemini_mod, "FIXTURE_DIR", tmp_path)
    c = connect()
    yield c
    cleanup_test_rows(c)
    c.close()


def _velhe_member_embedding(conn) -> list[float]:
    """A real seeded Velhe member's vector, so clustering sees true similarity."""
    row = conn.execute(
        """SELECT gr.embedding::text FROM cluster_memberships cm
           JOIN demand_clusters dc ON dc.id = cm.demand_cluster_id
           JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
           JOIN structured_requests sr ON sr.id = gr.structured_request_id
           WHERE dc.category = 'water_infrastructure'
             AND sr.raw_location_mention = 'Velhe' AND gr.embedding IS NOT NULL
           LIMIT 1""").fetchone()
    assert row, "seeded database required (seed.py)"
    return json.loads(row[0])


def _velhe_cluster(conn) -> str:
    return str(conn.execute(
        """SELECT dc.id FROM demand_clusters dc
           JOIN region_profiles rp ON ST_Contains(rp.boundary, dc.centroid)
           WHERE dc.category = 'water_infrastructure' AND rp.name = 'Velhe'
           LIMIT 1""").fetchone()[0])


@pytest.mark.parametrize("mention,expected", [
    ("वेल्हे गाँव", "वेल्हे"),
    ("Velhe village", "Velhe"),
    ("Paud gaon", "Paud"),
    ("वेल्हे मध्ये", "वेल्हे"),
    ("Ward 14 Hadapsar", "Hadapsar"),
])
def test_suffix_stripping(mention, expected):
    assert locate.strip_place_suffixes(mention) == expected


def test_village_suffix_resolves_to_velhe_and_joins_its_cluster(conn):
    """The README's known failure: "वेल्हे गाँव" geocodes to nothing live.
    The fallback resolves it to Velhe (medium, reason named) and the request
    joins the seeded Velhe water cluster."""
    sr = make_sr(conn, mention="वेल्हे गाँव",
                 text="test वेल्हे गाँव में पानी नहीं है")
    empty = lambda q: []  # both the raw and the stripped query find nothing
    vec = _velhe_member_embedding(conn)
    gr = locate.run(conn, sr, _transport=empty, _embedder=lambda t: vec)
    x, y, confidence, reason = conn.execute(
        """SELECT ST_X(geom), ST_Y(geom), confidence, confidence_reason
           FROM geocoded_requests WHERE id = %s""", (gr,)).fetchone()
    assert confidence == "medium"
    assert "matched known region 'Velhe'" in reason
    assert abs(y - 18.3036) < 0.01 and abs(x - 73.5825) < 0.01
    result = cluster_stage.run(conn, gr)
    assert result["cluster_id"] == _velhe_cluster(conn)


def test_suffix_stripped_query_is_geocoded_first(conn):
    queries = []

    def transport(q):
        queries.append(q)
        return [nominatim_result()] if q.startswith("Velhe,") else []

    sr = make_sr(conn, mention="Velhe village")
    gr = locate.run(conn, sr, _transport=transport, _embedder=lambda t: [0.5] * 768)
    confidence, reason = conn.execute(
        "SELECT confidence, confidence_reason FROM geocoded_requests WHERE id=%s",
        (gr,)).fetchone()
    assert queries[0].startswith("Velhe village") and queries[1].startswith("Velhe,")
    assert confidence == "medium" and "suffix-stripped mention 'Velhe'" in reason


def test_landmark_name_fallback(conn):
    sr = make_sr(conn, mention="near Aundh Health Centre 3")
    gr = locate.run(conn, sr, _transport=lambda q: [],
                    _embedder=lambda t: [0.5] * 768)
    confidence, reason = conn.execute(
        "SELECT confidence, confidence_reason FROM geocoded_requests WHERE id=%s",
        (gr,)).fetchone()
    # "Aundh" also matches the region; the region match is tried first and is
    # the coarser, safer answer.
    assert confidence == "medium" and "Aundh" in reason


def test_region_fallback_works_when_geocoder_is_down(conn):
    def down(q):
        raise ConnectionError("nominatim unreachable")
    sr = make_sr(conn, mention="पौड गाव")
    gr = locate.run(conn, sr, _transport=down, _embedder=lambda t: [0.5] * 768)
    confidence, reason = conn.execute(
        "SELECT confidence, confidence_reason FROM geocoded_requests WHERE id=%s",
        (gr,)).fetchone()
    assert confidence == "medium" and "'Paud'" in reason
    assert "geocoding service unavailable" in reason


def test_unknown_place_still_flagged_never_dropped(conn):
    sr = make_sr(conn, mention="Zzyzx Nowhere")
    gr = locate.run(conn, sr, _transport=lambda q: [],
                    _embedder=lambda t: [0.5] * 768)
    geom, confidence = conn.execute(
        "SELECT geom, confidence FROM geocoded_requests WHERE id=%s",
        (gr,)).fetchone()
    assert geom is None and confidence == "flagged"


def test_embedding_cache_never_stores_raw_pii(conn, tmp_path):
    sr = make_sr(conn, mention="Velhe", text="test मेरा नाम सुनीता है 9876543210 पानी")
    locate.run(conn, sr, _transport=lambda q: [nominatim_result()],
               _embedder=lambda t: [0.5] * 768)
    stored = "".join(p.read_text() for p in tmp_path.rglob("*.json"))
    assert "9876543210" not in stored and "सुनीता" not in stored
    assert "[PHONE]" in stored
