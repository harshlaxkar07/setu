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
    rehearsal or restart); a genuinely new text costs exactly one call.

    The cache is keyed on, and stores, the PII-masked text: it lives in the
    fixture store (committed for demo replay), so raw identifiers must never
    reach it (enhancements design D13). PII-free texts keep their old keys.
    """
    if not text:
        return None
    from app import pii
    text = pii.mask(text)[0]
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


# --- informal-location fallbacks (enhancements design D8) ---------------------

# Generic words around a place name that stop geocoders matching it:
# "वेल्हे गाँव", "Velhe village", "Paud gaon", "वेल्हे मध्ये".
_SUFFIX_WORDS = re.compile(
    r"\b(?:village|gaon|gaav|gav|gaanv|ward\s*(?:no\.?\s*)?\d+|me|mein|madhe)\b"
    r"|(?:गाँव|गांव|गाव|गावात|ग्राम|में|मध्ये|मधील|वार्ड\s*\d+)",
    re.IGNORECASE,
)


def strip_place_suffixes(mention: str) -> str:
    """The mention with generic village/ward/postposition words removed."""
    out = _SUFFIX_WORDS.sub(" ", mention)
    return re.sub(r"\s+", " ", out).strip(" ,.-।")


def _match_region(conn: psycopg.Connection, text: str):
    """(lon, lat, name) of a known region whose name or alias appears in text."""
    row = conn.execute(
        """SELECT ST_X(c), ST_Y(c), name FROM (
               SELECT COALESCE(centroid, ST_Centroid(boundary)) AS c, name,
                      array_prepend(name, aliases) AS names
               FROM region_profiles) r
           WHERE EXISTS (SELECT 1 FROM unnest(r.names) n
                         WHERE length(n) >= 3 AND %s ILIKE '%%' || n || '%%')
           ORDER BY name LIMIT 1""",
        (text,),
    ).fetchone()
    return row


def _match_facility(conn: psycopg.Connection, text: str):
    """(lon, lat, name) of a named facility/landmark matching the text."""
    if len(text) < 4:
        return None
    return conn.execute(
        """SELECT ST_X(geom), ST_Y(geom), name FROM infrastructure_facilities
           WHERE name IS NOT NULL
             AND (%s ILIKE '%%' || name || '%%' OR name ILIKE '%%' || %s || '%%')
           ORDER BY length(name) DESC LIMIT 1""",
        (text, text),
    ).fetchone()


def _fallback_locate(conn: psycopg.Connection, mention: str, transport, *,
                     try_geocoder: bool):
    """(lon, lat, reason) from the fallback chain, or None:
    geocoder on the suffix-stripped mention → known region names/aliases →
    named facilities/landmarks."""
    stripped = strip_place_suffixes(mention)
    if try_geocoder and stripped and stripped != mention.strip():
        try:
            best, _, _ = _assess(_geocode(compose_query(stripped), transport))
            if best is not None:
                return (float(best["lon"]), float(best["lat"]),
                        f"resolved via fallback: suffix-stripped mention "
                        f"'{stripped}' geocoded")
        except Exception:
            pass  # the database fallbacks below still apply
    for text in dict.fromkeys((mention, stripped)):
        if not text:
            continue
        region = _match_region(conn, text)
        if region is not None:
            return (region[0], region[1],
                    f"resolved via fallback: matched known region '{region[2]}'")
    for text in dict.fromkeys((stripped, mention)):
        facility = _match_facility(conn, text) if text else None
        if facility is not None:
            return (facility[0], facility[1],
                    f"resolved via fallback: matched landmark '{facility[2]}'")
    return None


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
        """SELECT sr.raw_location_mention, sr.summary, cr.raw_text, t.text,
                  cr.assisted_village
           FROM structured_requests sr
           JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
           LEFT JOIN transcriptions t ON t.citizen_request_id = cr.id
           WHERE sr.id = %s
           ORDER BY t.created_at DESC NULLS LAST LIMIT 1""",
        (structured_request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown structured_request {structured_request_id}")
    mention, summary, raw_text, transcription, village = row
    # Assisted reports (enhancements D11): the field worker's village is the
    # location when the message itself names none.
    if not (mention or "").strip() and village:
        mention = village

    # -- geocode -------------------------------------------------------------
    lon = lat = None
    if not (mention or "").strip():
        confidence, reason = "flagged", "no location mention in the request"
    else:
        service_down = False
        try:
            results = _geocode(compose_query(mention), transport)
            best, confidence, reason = _assess(results)
            if best is not None:
                lon, lat = float(best["lon"]), float(best["lat"])
        except Exception as exc:  # service down / timeout — flag, never drop
            service_down = True
            confidence, reason = "flagged", f"geocoding service unavailable: {exc}"
        if lon is None:
            # Informal-location fallbacks (enhancements design D8). Each one
            # resolves at medium confidence with the fallback named.
            found = _fallback_locate(conn, mention, transport,
                                     try_geocoder=not service_down)
            if found is not None:
                lon, lat, fallback_reason = found
                confidence = "medium"
                reason = f"{fallback_reason} (original: {reason})"

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
