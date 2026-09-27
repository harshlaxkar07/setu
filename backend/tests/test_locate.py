"""Locate stage tests (tasks 4.1, 4.4).

Nominatim is never called live: every test injects `_transport`. Embeddings
are never called live: every test injects `_embedder`. The throttle test is
the only one that pays real wall-clock time.
"""
import time
import uuid

import pytest

from app import gemini as gemini_mod
from app.constants import EMBEDDING_DIM
from app.stages import locate
from tests.conftest_a import (
    cleanup_test_rows,
    connect,
    make_citizen_request,
    make_structured_request,
)


def nominatim_result(lat="18.3036", lon="73.5824", display="Velhe, Pune",
                     importance=0.6, addresstype="village") -> dict:
    return {"lat": lat, "lon": lon, "display_name": display,
            "importance": importance, "addresstype": addresstype}


def transport_returning(results):
    """Fake transport that records the queries it was asked."""
    queries = []

    def _t(query):
        queries.append(query)
        return results

    _t.queries = queries
    return _t


def counting_embedder():
    calls = []

    def _e(text):
        calls.append(text)
        return [0.5] * EMBEDDING_DIM

    _e.calls = calls
    return _e


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    # Fast tests: no real 1 s spacing except in the dedicated throttle test.
    monkeypatch.setattr(locate, "MIN_INTERVAL_S", 0.0)
    # Keep geocode fixtures + embedding cache out of the shared fixture store.
    monkeypatch.setattr(locate, "FIXTURE_DIR", tmp_path)
    monkeypatch.setattr(gemini_mod, "FIXTURE_DIR", tmp_path)
    c = connect()
    yield c
    cleanup_test_rows(c)
    c.close()


def make_sr(conn, mention="Velhe", text=None) -> str:
    cr = make_citizen_request(conn, text=text or f"test paani {uuid.uuid4()}")
    return make_structured_request(conn, cr, mention=mention)


def geocoded_row(conn, gr_id):
    return conn.execute(
        """SELECT ST_X(geom), ST_Y(geom), confidence, confidence_reason,
                  vector_dims(embedding)
           FROM geocoded_requests WHERE id = %s""", (gr_id,)).fetchone()


# ------------------------------------------------------------- confidence

def test_single_result_is_high_confidence_with_geom(conn):
    t = transport_returning([nominatim_result()])
    sr = make_sr(conn, mention="Velhe")
    gr = locate.run(conn, sr, _transport=t, _embedder=counting_embedder())
    lon, lat, confidence, reason, dims = geocoded_row(conn, gr)
    assert confidence == "high" and reason is None
    assert abs(lon - 73.5824) < 1e-4 and abs(lat - 18.3036) < 1e-4
    assert dims == EMBEDDING_DIM
    # raw mention preserved unmodified on the StructuredRequest
    assert conn.execute(
        "SELECT raw_location_mention FROM structured_requests WHERE id = %s",
        (sr,)).fetchone()[0] == "Velhe"


def test_query_composited_with_pune_region_context(conn):
    t = transport_returning([nominatim_result()])
    sr = make_sr(conn, mention="government school ke paas, Testwadi")
    locate.run(conn, sr, _transport=t, _embedder=counting_embedder())
    assert t.queries == [
        "government school ke paas, Testwadi, Pune, Maharashtra, India"]
    # components already present are not duplicated
    assert locate.compose_query("Kothrud, Pune") == \
        "Kothrud, Pune, Maharashtra, India"


def test_multiple_candidates_is_medium_with_reason(conn):
    results = [
        nominatim_result(importance=0.4, display="Testwadi, Haveli"),
        nominatim_result(lat="18.40", lon="73.70", importance=0.7,
                         display="Testwadi, Mulshi"),
    ]
    sr = make_sr(conn, mention="Testwadi")
    gr = locate.run(conn, sr, _transport=transport_returning(results),
                    _embedder=counting_embedder())
    lon, lat, confidence, reason, _ = geocoded_row(conn, gr)
    assert confidence == "medium"
    assert "ambiguous" in reason and "2 candidate" in reason
    # best-effort selection = highest importance
    assert abs(lon - 73.70) < 1e-6 and abs(lat - 18.40) < 1e-6


def test_coarse_admin_level_is_medium(conn):
    sr = make_sr(conn, mention="somewhere vague")
    gr = locate.run(
        conn, sr,
        _transport=transport_returning(
            [nominatim_result(addresstype="state", display="Maharashtra")]),
        _embedder=counting_embedder())
    _, _, confidence, reason, _ = geocoded_row(conn, gr)
    assert confidence == "medium" and "coarse" in reason


# -------------------------------------------------- flag-never-drop posture

def test_no_result_proceeds_flagged_with_null_geom(conn):
    sr = make_sr(conn, mention="Nonexistentpur")
    gr = locate.run(conn, sr, _transport=transport_returning([]),
                    _embedder=counting_embedder())
    lon, lat, confidence, reason, dims = geocoded_row(conn, gr)
    assert (lon, lat) == (None, None)
    assert confidence == "flagged"
    assert "could not be resolved" in reason
    assert dims == EMBEDDING_DIM  # still embedded: stays clusterable/queryable


def test_service_failure_proceeds_flagged(conn):
    def broken(query):
        raise ConnectionError("nominatim down")

    sr = make_sr(conn)
    gr = locate.run(conn, sr, _transport=broken,
                    _embedder=counting_embedder())
    lon, lat, confidence, reason, _ = geocoded_row(conn, gr)
    assert (lon, lat) == (None, None)
    assert confidence == "flagged" and "unavailable" in reason


def test_empty_mention_proceeds_flagged_without_geocode_call(conn):
    t = transport_returning([nominatim_result()])
    sr = make_sr(conn, mention="")
    gr = locate.run(conn, sr, _transport=t, _embedder=counting_embedder())
    _, _, confidence, reason, _ = geocoded_row(conn, gr)
    assert confidence == "flagged" and "no location mention" in reason
    assert t.queries == []  # nothing to geocode


# ------------------------------------------------------------------ throttle

def test_consecutive_geocodes_spaced_at_least_one_second(conn, monkeypatch):
    monkeypatch.setattr(locate, "MIN_INTERVAL_S", 1.0)
    monkeypatch.setattr(locate, "_last_call", 0.0)
    t = transport_returning([nominatim_result()])
    stamps = []

    def stamping(query):
        stamps.append(time.monotonic())
        return t(query)

    locate._geocode("test throttle q1", stamping)
    locate._geocode("test throttle q2", stamping)
    assert len(stamps) == 2
    assert stamps[1] - stamps[0] >= 1.0  # >= 1 req/s, serialized never dropped


# ----------------------------------------------- embedding cache (task 4.4)

def test_new_submission_costs_exactly_one_embedding_call(conn):
    embedder = counting_embedder()
    text = f"test bilkul naya paani complaint {uuid.uuid4()}"
    sr = make_sr(conn, text=text)
    locate.run(conn, sr, _transport=transport_returning([nominatim_result()]),
               _embedder=embedder)
    assert embedder.calls == [text]  # one call, on the citizen's own words


def test_repeat_of_cached_text_costs_zero_embedding_calls(conn):
    """Rehearsals/restarts replay the same inputs: the disk cache answers,
    the embedding client is never called again (design D5)."""
    embedder = counting_embedder()
    text = f"test rehearsed line {uuid.uuid4()}"
    t = transport_returning([nominatim_result()])

    sr1 = make_sr(conn, text=text)
    locate.run(conn, sr1, _transport=t, _embedder=embedder)
    assert len(embedder.calls) == 1

    # same text again — a rehearsal rerun / post-restart replay
    sr2 = make_sr(conn, text=text)
    gr2 = locate.run(conn, sr2, _transport=t, _embedder=embedder)
    assert len(embedder.calls) == 1  # zero new calls
    assert geocoded_row(conn, gr2)[4] == EMBEDDING_DIM  # vector still stored
