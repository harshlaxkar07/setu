"""Locate stage: StructuredRequest → GeocodedRequest (files/05 stage 2).

- Nominatim/OpenStreetMap geocoding (ADR-006) with a module-level throttle
  enforcing >= 1 request/second across the whole process; concurrent callers
  are serialized, never rejected (geospatial spec "respects the Nominatim
  rate limit").
- Confidence: exactly one candidate at a sensible level → high; multiple
  candidates or a coarser-than-expected admin level → medium with the
  ambiguity stated; no result / service failure → NULL geom + flagged, and
  the request PROCEEDS (flag, never drop).
- Geocode results are recorded to a local fixture store (same posture as the
  Gemini replay layer, design D5): DEMO_REPLAY=1 consults fixtures first, so
  the rehearsed demo cannot be sunk by live Nominatim.
- The request embedding is computed here (Gemini text-embedding-004 via
  langchain_google_genai) UNLESS a cached vector exists — a per-text disk
  cache means rehearsals and restarts cost zero embedding calls; only a
  genuinely new submission costs one (design D5, task 4.4).

Tests inject `_transport` (geocoding) and `_embedder` (embeddings): neither
live service is ever called from the test suite.
"""
import hashlib
import json
import re
import threading
import time

import psycopg

from app.constants import EMBEDDING_DIM
from app.gemini import FIXTURE_DIR, _replay_enabled

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "setu-hackathon-demo/0.1 (civic infrastructure demand aggregation)"

# Minimum spacing between outbound geocoding calls. Module-level so every
# caller in the process shares one throttle. Tests that don't exercise the
# throttle may monkeypatch this to 0 to stay fast.
MIN_INTERVAL_S = 1.0

# Nominatim addresstypes coarser than any street/village/ward-level mention —
# resolving only to these means the mention wasn't really located.
_COARSE_LEVELS = {"state", "country", "state_district", "county"}

_throttle_lock = threading.Lock()
_last_call = 0.0  # monotonic timestamp of the previous outbound call


def _throttle() -> None:
    """Block until >= MIN_INTERVAL_S has passed since the previous call.

    Serializes concurrent geocodes (lock) instead of rejecting any — a burst
    of submissions is spaced out, never dropped (spec scenario).
    """
    global _last_call
    with _throttle_lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def compose_query(mention: str) -> str:
    """Composite the raw mention with region context: Pune district, India.

    Components already present in the mention (case-insensitive) are not
    duplicated, so "Kothrud, Pune" becomes "Kothrud, Pune, Maharashtra, India"
    rather than repeating "Pune".
    """
    parts = [mention.strip()]
    for ctx in ("Pune", "Maharashtra", "India"):
        # Word-boundary match: "Punegaon" must still get ", Pune" appended.
        if not re.search(rf"\b{re.escape(ctx)}\b", mention, re.IGNORECASE):
            parts.append(ctx)
    return ", ".join(parts)


def _live_transport(query: str) -> list[dict]:
    """Default transport: one throttled GET against public Nominatim."""
    import httpx

    resp = httpx.get(
        NOMINATIM_URL,
        params={"q": query, "format": "jsonv2", "limit": 5, "addressdetails": 0},
        headers={"User-Agent": USER_AGENT},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


# --- geocode fixture store (design D5's cacheable Nominatim results) ---------

def _geo_fixture_path(query: str):
    key = hashlib.sha256(query.encode()).hexdigest()
    return FIXTURE_DIR / "geocode" / f"{key}.json"


def _geocode(query: str, transport) -> list[dict]:
    """Throttled, fixture-aware geocode. Returns Nominatim result dicts."""
    if _replay_enabled():
        path = _geo_fixture_path(query)
        if path.exists():
            return json.loads(path.read_text())["results"]
    _throttle()
    results = transport(query)
    try:
        path = _geo_fixture_path(query)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"query": query, "results": results}))
    except OSError:
        pass  # fixture recording is best-effort
    return results


# --- embedding with per-text disk cache (design D5, task 4.4) ----------------

_EMBED_CACHE_DIR = "embeddings"


def _embed_cache_path(text: str):
    key = hashlib.sha256(text.encode()).hexdigest()
    return FIXTURE_DIR / _EMBED_CACHE_DIR / f"{key}.json"


def _live_embedder(text: str) -> list[float]:
    # Through the configured provider (PII-masked, dimension-checked).
    from app import llm
    return llm.embed(text)


def _embedding_for(text: str, embedder) -> list[float] | None:
    """Vector for `text`, from cache when available (zero API calls on a
    rehearsal or restart); a genuinely new text costs exactly one call."""
    if not text:
        return None
    cache = _embed_cache_path(text)
    if cache.exists():
        return json.loads(cache.read_text())["embedding"]
    vec = embedder(text)
    if len(vec) != EMBEDDING_DIM:
        raise ValueError(f"embedding has {len(vec)} dims, expected {EMBEDDING_DIM}")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"text": text, "embedding": vec}))
    except OSError:
        pass
    return vec


# --- confidence assessment ----------------------------------------------------

def _assess(results: list[dict]) -> tuple[dict | None, str, str | None]:
    """(best candidate, confidence, reason) from Nominatim results.

    - exactly one candidate at a usable level → high, no reason
    - multiple candidates → best-effort first pick, medium, ambiguity stated
    - only a coarse admin-level match (state/county) → medium with reason
    - nothing → (None, flagged, reason)
    """
    if not results:
        return None, "flagged", "location could not be resolved: no geocoding result"
    best = max(results, key=lambda r: float(r.get("importance", 0.0)))
    coarse = best.get("addresstype", best.get("type", "")) in _COARSE_LEVELS
    if len(results) > 1:
        names = "; ".join(r.get("display_name", "?") for r in results[:3])
        return best, "medium", (
            f"ambiguous: {len(results)} candidate places returned "
            f"(top candidates: {names}); best-effort selection"
        )
    if coarse:
        return best, "medium", (
            "resolved only to a coarse administrative level "
            f"({best.get('addresstype', best.get('type'))}), "
            "coarser than the mention implies"
        )
    return best, "high", None


def run(conn: psycopg.Connection, structured_request_id: str, *,
        _transport=None, _embedder=None) -> str:
    """Produce a GeocodedRequest; returns geocoded_request_id.

    Never raises on a geocoding failure: the request proceeds with NULL geom,
    confidence flagged, and a stated reason (geospatial spec "Geocoding
    failure proceeds flagged, never dropped"). The raw location mention on the
    StructuredRequest is never modified.
    """
    transport = _transport or _live_transport
    embedder = _embedder or _live_embedder

    row = conn.execute(
        """SELECT sr.raw_location_mention, sr.summary, cr.raw_text, t.text
           FROM structured_requests sr
           JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
           LEFT JOIN transcriptions t ON t.citizen_request_id = cr.id
           WHERE sr.id = %s
           ORDER BY t.created_at DESC NULLS LAST LIMIT 1""",
        (structured_request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown structured_request {structured_request_id}")
    mention, summary, raw_text, transcription = row

    # -- geocode -------------------------------------------------------------
    lon = lat = None
    if not (mention or "").strip():
        confidence, reason = "flagged", "no location mention in the request"
    else:
        try:
            results = _geocode(compose_query(mention), transport)
            best, confidence, reason = _assess(results)
            if best is not None:
                lon, lat = float(best["lon"]), float(best["lat"])
        except Exception as exc:  # service down / timeout — flag, never drop
            confidence, reason = "flagged", f"geocoding service unavailable: {exc}"

    # -- embedding (cached; the citizen's own words, matching the seed) -------
    embed_text = raw_text or transcription or summary
    embedding = _embedding_for(embed_text, embedder)

    gr = conn.execute(
        """INSERT INTO geocoded_requests
             (structured_request_id, geom, confidence, confidence_reason,
              embedding)
           VALUES (%s,
                   CASE WHEN %s::float8 IS NULL THEN NULL
                        ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326) END,
                   %s, %s, %s::vector)
           RETURNING id""",
        (structured_request_id, lon, lon, lat, confidence, reason,
         json.dumps(embedding) if embedding is not None else None),
    ).fetchone()
    conn.commit()
    return str(gr[0])
