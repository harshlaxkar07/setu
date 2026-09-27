#!/usr/bin/env python3
"""Seed the Setu demo database: the Pune Region A/B contrast (design D7).

Run inside the backend container (it has the dependencies and DATABASE_URL):

    docker compose exec backend python /app/seed/seed.py

Seeds, deterministically (fixed RNG seed — task 2.8 reproducibility):
  - infrastructure_datasets + region_profiles (Census-2011-proportioned, cited)
  - infrastructure_facilities: 10 functioning water points inside Region A's
    service radius, 0 inside Region B's
  - ~500 Region A / ~20 Region B synthetic Hindi/Hinglish water complaints as
    citizen_requests + structured_requests + geocoded_requests
  - the two DemandClusters with memberships, counts, summaries, and Region B's
    under-representation PriorityIndicator
  - embeddings via Gemini text-embedding-004, computed once and cached to a
    local fixture file so re-seeding costs zero API calls (design D5). Without
    GEMINI_API_KEY the seed completes but leaves embeddings NULL and exits 2.
  - a Fuse/Score pass over both clusters once the stages exist (task 2.7).

Re-running truncates and rebuilds all derived tables — identical demo state.
"""
import hashlib
import json
import math
import os
import random
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, "/app")  # backend container: app package + mounted seed dir
from app.constants import (  # noqa: E402
    CATEGORY_WATER,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    SERVICE_RADIUS_M,
)

HERE = Path(__file__).parent
LOCATIONS = json.loads((HERE / "locations.json").read_text())
EMBED_CACHE = HERE / "embedding_cache.json"

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://setu:setu_local_dev@localhost:5434/setu"
)

RNG = random.Random(20260926)  # fixed: reproducible seed state (task 2.8)

N_REGION_A = 500
N_REGION_B = 20

# Synthetic Hindi/Hinglish water-complaint templates (files/04 worked example).
TEMPLATES = [
    "{place} में कई हफ़्तों से पीने का पानी ठीक से नहीं आ रहा है।",
    "{place} में पानी की सप्लाई बहुत कम आ रही है, हफ़्ते में सिर्फ {n} दिन।",
    "हमारे इलाक़े {place} में नल सूखे पड़े हैं, टैंकर भी नहीं आ रहा।",
    "{place} me paani nahi aa raha hai kai hafton se, bahut dikkat hai.",
    "Paani ki supply {place} me bilkul kharab hai, {n} din se nal sukha hai.",
    "{place} में बोरवेल ख़राब है और पीने के पानी की बड़ी समस्या है।",
    "Hamare {place} me drinking water ki bahut problem hai, please dekho.",
    "{place} में पानी गंदा आ रहा है, पीने लायक़ नहीं है।",
]
SUMMARY = "Drinking water supply inadequate or absent in {place} for weeks"


def jitter(lat: float, lon: float, max_m: float) -> tuple[float, float]:
    """Random point within max_m metres of (lat, lon) — deterministic via RNG."""
    r = max_m * math.sqrt(RNG.random())
    theta = RNG.random() * 2 * math.pi
    dlat = (r * math.cos(theta)) / 111_320.0
    dlon = (r * math.sin(theta)) / (111_320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def make_requests(region: dict, n: int, place_short: str) -> list[dict]:
    out = []
    for i in range(n):
        text = RNG.choice(TEMPLATES).format(place=place_short, n=RNG.randint(2, 20))
        lat, lon = jitter(region["lat"], region["lon"], 1200)
        out.append({
            "text": text,
            "lat": lat,
            "lon": lon,
            "submitter": f"seed-{place_short.lower()}-{i:04d}",
            "language": "Hinglish" if text[0].isascii() else "Hindi",
        })
    return out


def load_embed_cache() -> dict:
    if EMBED_CACHE.exists():
        return json.loads(EMBED_CACHE.read_text())
    return {}


def embed_texts(texts: list[str]) -> dict[str, list[float]] | None:
    """text → 768-dim vector via text-embedding-004, through a local cache.

    Only cache misses hit the API (computed once — design D5). Returns None
    when no GEMINI_API_KEY is configured and misses exist.
    """
    cache = load_embed_cache()
    keyed = {hashlib.sha256(t.encode()).hexdigest(): t for t in texts}
    misses = [t for k, t in keyed.items() if k not in cache]
    if misses:
        if not os.environ.get("GEMINI_API_KEY"):
            print(f"!! {len(misses)} embeddings needed but GEMINI_API_KEY is unset.")
            return None
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        client = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
        print(f"Embedding {len(misses)} new texts via {EMBEDDING_MODEL} ...")
        # embed_documents batches internally; free-tier-friendly chunks.
        for start in range(0, len(misses), 50):
            chunk = misses[start:start + 50]
            # gemini-embedding-001 defaults to 3072 dims; the schema column
            # is vector(768), so request the reduced dimensionality.
            vecs = client.embed_documents(chunk,
                                          output_dimensionality=EMBEDDING_DIM)
            for t, vec in zip(chunk, vecs):
                assert len(vec) == EMBEDDING_DIM
                cache[hashlib.sha256(t.encode()).hexdigest()] = vec
        EMBED_CACHE.write_text(json.dumps(cache))
    return {t: cache[k] for k, t in keyed.items()}


def main() -> int:
    conn = psycopg.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    print("Resetting derived tables ...")
    # citizen_requests is immutable by trigger; a full reseed disables the
    # trigger transiently — the ONLY sanctioned mutation path, seed-time only.
    cur.execute("ALTER TABLE citizen_requests DISABLE TRIGGER citizen_requests_immutable")
    cur.execute("""
        TRUNCATE approvals, recommendations, priority_scores, priority_indicators,
                 gap_scores, verification_records, run_traces, cluster_memberships,
                 demand_clusters, geocoded_requests, structured_requests,
                 transcriptions, citizen_requests, infrastructure_facilities,
                 region_profiles, infrastructure_datasets CASCADE
    """)
    cur.execute("ALTER TABLE citizen_requests ENABLE TRIGGER citizen_requests_immutable")

    ra, rb = LOCATIONS["region_a"], LOCATIONS["region_b"]
    place_a = ra["query"].split(",")[0]          # "Kothrud"
    place_b = rb["query"].split(",")[0]          # "Velhe"

    # --- datasets & region profiles (task 2.2) ------------------------------
    print("Seeding datasets and region profiles ...")
    cur.execute(
        """INSERT INTO infrastructure_datasets (name, coverage_area, last_updated)
           VALUES (%s, %s, %s) RETURNING id""",
        ("Synthetic demographics (proportioned to Census 2011, Pune district)",
         "Pune district", "2011-03-01"),
    )
    ds_pop = cur.fetchone()[0]
    cur.execute(
        """INSERT INTO infrastructure_datasets (name, coverage_area, last_updated)
           VALUES (%s, %s, %s) RETURNING id""",
        ("Synthetic water facility register (demo seed)", "Pune district", "2026-09-01"),
    )
    ds_fac = cur.fetchone()[0]

    # Census 2011: Kothrud-scale urban wards run ~1.5-2 lakh; Velhe-scale
    # villages a few thousand. Proportioned, openly synthetic (files/08 §1).
    cur.execute(
        """INSERT INTO region_profiles
             (name, boundary, population, investment_label, dataset_id)
           VALUES
             (%s, ST_Buffer(ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, 2500)::geometry,
              %s, %s, %s) RETURNING id""",
        (place_a, ra["lon"], ra["lat"], 175000, "high", ds_pop),
    )
    cur.execute(
        """INSERT INTO region_profiles
             (name, boundary, population, investment_label, dataset_id)
           VALUES
             (%s, ST_Buffer(ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, 2500)::geometry,
              %s, %s, %s) RETURNING id""",
        (place_b, rb["lon"], rb["lat"], 4800, "low", ds_pop),
    )

    # --- facilities (task 2.3) ----------------------------------------------
    print("Seeding facilities: 10 in Region A radius, 0 in Region B ...")
    for _ in range(10):
        lat, lon = jitter(ra["lat"], ra["lon"], SERVICE_RADIUS_M * 0.8)
        cur.execute(
            """INSERT INTO infrastructure_facilities
                 (dataset_id, facility_type, geom, functioning)
               VALUES (%s, 'water_point', ST_SetSRID(ST_MakePoint(%s,%s),4326), true)""",
            (ds_fac, lon, lat),
        )

    # --- citizen/structured/geocoded requests (task 2.4) --------------------
    print(f"Seeding {N_REGION_A}+{N_REGION_B} synthetic requests ...")
    reqs_a = make_requests(ra, N_REGION_A, place_a)
    reqs_b = make_requests(rb, N_REGION_B, place_b)
    embeddings = embed_texts([r["text"] for r in reqs_a + reqs_b])

    cluster_ids = {}
    for region, place, reqs, conf in (
        (ra, place_a, reqs_a, "high"),
        (rb, place_b, reqs_b, "high"),
    ):
        # DemandCluster (task 2.6)
        cur.execute(
            """INSERT INTO demand_clusters
                 (category, centroid, representative_summary, member_count,
                  status, confidence)
               VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), %s, %s, 'active', %s)
               RETURNING id""",
            (CATEGORY_WATER, region["lon"], region["lat"],
             SUMMARY.format(place=place), len(reqs), conf),
        )
        cluster_id = cur.fetchone()[0]
        cluster_ids[place] = cluster_id

        for r in reqs:
            cur.execute(
                """INSERT INTO citizen_requests (channel, raw_text, submitter_ref)
                   VALUES ('text', %s, %s) RETURNING id""",
                (r["text"], r["submitter"]),
            )
            cr_id = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO structured_requests
                     (citizen_request_id, category, urgency, summary,
                      detected_language, raw_location_mention)
                   VALUES (%s, %s, 'high', %s, %s, %s) RETURNING id""",
                (cr_id, CATEGORY_WATER, SUMMARY.format(place=place),
                 r["language"], place),
            )
            sr_id = cur.fetchone()[0]
            vec = embeddings.get(r["text"]) if embeddings else None
            cur.execute(
                """INSERT INTO geocoded_requests
                     (structured_request_id, geom, confidence, embedding)
                   VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), 'high', %s)
                   RETURNING id""",
                (sr_id, r["lon"], r["lat"], vec),
            )
            gr_id = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO cluster_memberships
                     (geocoded_request_id, demand_cluster_id, similarity_score)
                   VALUES (%s, %s, %s)""",
                (gr_id, cluster_id, round(0.86 + RNG.random() * 0.1, 4)),
            )

    # Region B's under-representation signal (task 2.6; files/04 worked example).
    cur.execute(
        """INSERT INTO priority_indicators
             (demand_cluster_id, name, value_text, value_numeric, source_citations)
           VALUES (%s, %s, %s, %s, %s)""",
        (cluster_ids[place_b], "possible under-representation signal",
         f"low digital-reporting volume ({N_REGION_B} requests) flagged as a "
         "possible under-representation signal, not evidence of low need",
         N_REGION_B, json.dumps([{"dataset": "seed", "note": "files/04 worked example"}])),
    )

    conn.commit()

    # --- Fuse/Score pass (task 2.7) — once the stages exist ------------------
    try:
        from app.stages.fuse import fuse_cluster
        from app.stages.score import score_category
        print("Running Fuse/Score over both seeded clusters ...")
        with psycopg.connect(DATABASE_URL) as c2:
            for cid in cluster_ids.values():
                fuse_cluster(c2, cid)
            score_category(c2, CATEGORY_WATER)
            c2.commit()
        scored = True
    except ImportError:
        print("(Fuse/Score stages not built yet — task 2.7 pass skipped.)")
        scored = False

    print("\nSeed complete:")
    print(f"  Region A ({place_a}): {N_REGION_A} requests, 10 facilities, investment=high")
    print(f"  Region B ({place_b}): {N_REGION_B} requests, 0 facilities, investment=low")
    if embeddings is None:
        print("  EMBEDDINGS MISSING — set GEMINI_API_KEY and re-run (task 2.5).")
        return 2
    if not scored:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
