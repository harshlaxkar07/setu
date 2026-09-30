"""Import real facilities from OpenStreetMap (enhancements design D6).

Queries the Overpass API for one category's facilities inside a bounding box
and stores them as ONE new infrastructure dataset (source='openstreetmap',
imported_at=now) in a single transaction. Network or parse failure raises
before anything is written — no partial dataset is ever left behind.

Imported data is additive: Fuse/Score keep using the synthetic seed dataset
unless the operator sets SCORING_DATASET=openstreetmap (app.stages.fuse).
"""
import json

import httpx
import psycopg

from app.constants import CATEGORY_HEALTH, CATEGORY_WATER

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "setu-hackathon-demo/0.1 (civic infrastructure demand aggregation)"

# Pune district, roughly (south, west, north, east).
PUNE_DISTRICT_BBOX = (17.9, 73.3, 19.4, 75.1)

# category → (facility_type, Overpass tag filters)
CATEGORY_TAGS: dict[str, tuple[str, list[str]]] = {
    CATEGORY_HEALTH: ("health_facility",
                      ['["amenity"~"^(hospital|clinic|doctors)$"]',
                       '["healthcare"~"^(hospital|clinic|centre)$"]']),
    CATEGORY_WATER: ("water_point",
                     ['["amenity"="drinking_water"]',
                      '["man_made"~"^(water_tap|water_well|water_tower)$"]']),
}


class ImportFailed(RuntimeError):
    """The import could not complete; nothing was written."""


def build_query(category: str, bbox: tuple[float, float, float, float]) -> str:
    if category not in CATEGORY_TAGS:
        raise ValueError(f"no OpenStreetMap mapping for category {category!r} "
                         f"(supported: {', '.join(CATEGORY_TAGS)})")
    s, w, n, e = bbox
    area = f"({s},{w},{n},{e})"
    parts = "".join(f"{kind}{tag}{area};"
                    for tag in CATEGORY_TAGS[category][1] for kind in ("node", "way"))
    return f"[out:json][timeout:60];({parts});out center tags;"


def _live_transport(query: str) -> dict:
    resp = httpx.post(OVERPASS_URL, data={"data": query},
                      headers={"User-Agent": USER_AGENT}, timeout=90.0)
    resp.raise_for_status()
    return resp.json()


def parse_elements(payload: dict) -> list[dict]:
    """[{lat, lon, name}] from Overpass nodes and way centres, de-duplicated."""
    out, seen = [], set()
    for el in payload.get("elements", []):
        if el.get("type") == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            centre = el.get("center") or {}
            lat, lon = centre.get("lat"), centre.get("lon")
        if lat is None or lon is None:
            continue
        key = (el.get("type"), el.get("id"))
        if key in seen:
            continue
        seen.add(key)
        tags = el.get("tags") or {}
        out.append({"lat": float(lat), "lon": float(lon),
                    "name": tags.get("name:en") or tags.get("name")})
    return out


def import_category(conn: psycopg.Connection, category: str,
                    bbox: tuple[float, float, float, float] = PUNE_DISTRICT_BBOX,
                    *, transport=None) -> dict:
    """Fetch and store one category. Returns {dataset_id, facilities}."""
    query = build_query(category, bbox)
    try:
        payload = (transport or _live_transport)(query)
        facilities = parse_elements(payload)
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, KeyError) as exc:
        raise ImportFailed(f"OpenStreetMap unavailable or returned bad data: {exc}") from exc
    if not facilities:
        raise ImportFailed("OpenStreetMap returned no facilities for this area")

    ftype = CATEGORY_TAGS[category][0]
    with conn.transaction():
        (dataset_id,) = conn.execute(
            """INSERT INTO infrastructure_datasets
                 (name, coverage_area, last_updated, source, imported_at)
               VALUES (%s, %s, current_date, 'openstreetmap', now())
               RETURNING id""",
            (f"OpenStreetMap {category.replace('_', ' ')} (© OpenStreetMap contributors)",
             f"bbox {bbox}"),
        ).fetchone()
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO infrastructure_facilities
                     (dataset_id, facility_type, geom, functioning, name)
                   VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), true, %s)""",
                [(dataset_id, ftype, f["lon"], f["lat"], f["name"]) for f in facilities],
            )
    return {"dataset_id": str(dataset_id), "facilities": len(facilities)}
