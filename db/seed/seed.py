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
    CATEGORY_HEALTH,
    CATEGORY_ROAD,
    CATEGORY_WATER,
    EMBEDDING_DIM,
    SERVICE_RADIUS_M,
)

HERE = Path(__file__).parent
LOCATIONS = json.loads((HERE / "locations.json").read_text())
EMBED_CACHE = HERE / "embedding_cache.json"

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://setu:setu_local_dev@localhost:5434/setu"
)

RNG = random.Random(20260926)  # fixed: reproducible seed state (task 2.8)
# Separate generator for arrival times (enhancements D9/trends): seeded
# complaints arrive over the last HISTORY_DAYS instead of all "now". Kept
# apart from RNG so texts, positions and cached embeddings are unchanged.
HIST = random.Random(20260930)
HISTORY_DAYS = 60


def arrival_time():
    """A past arrival within HISTORY_DAYS (never inside the last hour, so the
    Trust stage's spike/burst windows see a realistic baseline)."""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone.utc) - timedelta(
        hours=HIST.uniform(1, HISTORY_DAYS * 24))

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

# --- enhancements: healthcare + road equity pairs and silent villages -------
# (enhancements design D3/D5). Coordinates verified against Nominatim
# 2026-09-30. Each category mirrors the water worked example: a high-volume,
# well-served urban ward vs a low-volume, underserved rural village. Silent
# villages have NO requests at all — they exist only in the region data.
# vulnerability/connectivity are synthetic 0..1 context indices.
EXTRA_REGIONS = [
    # name,     lat,        lon,        population, investment, settlement, vuln, conn
    ("Aundh",    18.5618834, 73.8101957, 120000, "high", "urban", 0.20, 0.90),
    ("Paud",     18.5242717, 73.6155138,   6000, "low",  "rural", 0.70, 0.35),
    ("Hadapsar", 18.5007741, 73.9379146, 250000, "high", "urban", 0.30, 0.85),
    ("Ghisar",   18.2926017, 73.5582518,   2500, "low",  "rural", 0.75, 0.25),
    ("Kurunji",  18.2194053, 73.7165880,   3200, "low",  "rural", 0.80, 0.20),
    ("Pabe",     18.3213235, 73.6651950,   4100, "low",  "rural", 0.72, 0.30),
    ("Tamhini",  18.4388230, 73.4395128,   1900, "low",  "rural", 0.85, 0.15),
]
# Devanagari / alternate spellings, matched by Locate's region fallback.
REGION_ALIASES = {
    "Kothrud": ["कोथरूड", "Kothrud"], "Velhe": ["वेल्हे", "वेल्हा", "Velha", "Vélhe"],
    "Aundh": ["औंध"], "Paud": ["पौड", "Poud"], "Hadapsar": ["हडपसर"],
    "Ghisar": ["घिसर"], "Kurunji": ["कुरुंजी", "Kurunjee"], "Pabe": ["पाबे"],
    "Tamhini": ["ताम्हिणी", "ताम्हिनी"],
}
# Context indices for the original worked-example regions.
BASE_REGION_CONTEXT = {"Kothrud": ("urban", 0.15, 0.92), "Velhe": ("rural", 0.68, 0.30)}

# Facilities per (region, facility_type): urban wards are served in every
# category; the rural pair villages lack their own category's facility.
EXTRA_FACILITIES = {
    ("Kothrud", "health_facility"): 7, ("Kothrud", "road_access_point"): 9,
    ("Aundh", "health_facility"): 8, ("Aundh", "water_point"): 9,
    ("Aundh", "road_access_point"): 8,
    ("Hadapsar", "road_access_point"): 12, ("Hadapsar", "water_point"): 11,
    ("Hadapsar", "health_facility"): 6,
    # Velhe and Ghisar are ~2.9 km apart (< 2 × service radius): neither gets
    # a facility of the other's pair category, or it could land inside the
    # other's radius and break the worked example.
    ("Velhe", "health_facility"): 1,
    ("Paud", "water_point"): 2, ("Paud", "road_access_point"): 1,
}
FACILITY_LABEL = {"health_facility": "Health Centre", "water_point": "Water Point",
                  "road_access_point": "Road Access Point"}

# (category, urban ward, n, rural village, n) — the equity pairs.
EXTRA_PAIRS = [
    (CATEGORY_HEALTH, "Aundh", 300, "Paud", 15),
    (CATEGORY_ROAD, "Hadapsar", 400, "Ghisar", 12),
]
# No {n} placeholders: few unique texts, so few embedding calls.
CATEGORY_TEMPLATES = {
    CATEGORY_HEALTH: [
        "{place} में पास में कोई अस्पताल नहीं है, इलाज के लिए बहुत दूर जाना पड़ता है।",
        "{place} के स्वास्थ्य केंद्र में डॉक्टर नहीं आते, दवाइयाँ भी नहीं मिलतीं।",
        "{place} me koi clinic nahi hai, bimar logon ko shahar le jana padta hai.",
        "{place} मध्ये दवाखाना नाही, उपचारासाठी खूप लांब जावे लागते.",
        "Hospital {place} se bahut door hai, delivery ke time bahut dikkat hoti hai.",
        "{place} में रात को कोई डॉक्टर नहीं मिलता, एम्बुलेंस भी देर से आती है।",
    ],
    CATEGORY_ROAD: [
        "{place} की सड़क महीनों से टूटी है, एम्बुलेंस भी ठीक से नहीं आ पाती।",
        "{place} me road bahut kharab hai, baarish me poora rasta band ho jata hai.",
        "{place} मधला रस्ता पूर्ण खराब झाला आहे, शाळेत जायला मुलांना त्रास होतो.",
        "{place} की सड़क पर बड़े गड्ढे हैं, रोज़ दुर्घटना का ख़तरा रहता है।",
        "Monsoon me {place} ka rasta toot jata hai, gaon se bahar nikalna mushkil hai.",
        "{place} तक पक्की सड़क नहीं है, बस भी नहीं आती।",
    ],
}
CATEGORY_SUMMARY = {
    CATEGORY_HEALTH: "No accessible health facility or doctor available in {place}",
    CATEGORY_ROAD: "Road to {place} damaged, blocking emergency and daily access",
}


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
        if (os.environ.get("LLM_PROVIDER") or "gemini") == "gemini" and \
                not os.environ.get("GEMINI_API_KEY"):
            print(f"!! {len(misses)} embeddings needed but GEMINI_API_KEY is unset.")
            return None
        from app import llm  # configured provider (enhancements design D16)
        provider = llm.get_provider()
        print(f"Embedding {len(misses)} new texts via "
              f"{provider.name}/{provider.embed_model} ...")
        # Free-tier-friendly chunks.
        for start in range(0, len(misses), 50):
            chunk = misses[start:start + 50]
            vecs = llm.embed_many(chunk)
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
        TRUNCATE decision_log, trust_flags, approvals, recommendations, priority_scores, priority_indicators,
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

    # Context attributes for the worked-example regions (enhancements D3).
    for name, (settlement, vuln, conn_idx) in BASE_REGION_CONTEXT.items():
        cur.execute(
            """UPDATE region_profiles
                  SET centroid = ST_Centroid(boundary), settlement_type = %s,
                      vulnerability_index = %s, connectivity_index = %s
                WHERE name = %s""",
            (settlement, vuln, conn_idx, name),
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
            at = r.get("at") or arrival_time()
            cur.execute(
                """INSERT INTO citizen_requests
                     (channel, raw_text, submitter_ref, created_at)
                   VALUES ('text', %s, %s, %s) RETURNING id""",
                (r["text"], r["submitter"], at),
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
                     (geocoded_request_id, demand_cluster_id, similarity_score,
                      created_at)
                   VALUES (%s, %s, %s, %s)""",
                (gr_id, cluster_id, round(0.86 + RNG.random() * 0.1, 4), at),
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

    seed_enhancement_regions(cur, ds_pop, ds_fac)
    for name, aliases in REGION_ALIASES.items():
        cur.execute("UPDATE region_profiles SET aliases = %s WHERE name = %s",
                    (aliases, name))
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
            # Enhancement categories: every cluster of each, then its scores.
            for category, *_ in EXTRA_PAIRS:
                for (cid,) in c2.execute(
                        "SELECT id FROM demand_clusters WHERE category = %s",
                        (category,)).fetchall():
                    fuse_cluster(c2, cid)
                score_category(c2, category)
            c2.commit()
            seed_resolved_example(c2)
            c2.commit()
        scored = True
    except ImportError:
        print("(Fuse/Score stages not built yet — task 2.7 pass skipped.)")
        scored = False

    print("\nSeed complete:")
    print(f"  Region A ({place_a}): {N_REGION_A} requests, 10 facilities, investment=high")
    print(f"  Region B ({place_b}): {N_REGION_B} requests, 0 facilities, investment=low")
    for category, urban, n_u, rural, n_r in EXTRA_PAIRS:
        print(f"  {category}: {urban} {n_u} requests vs {rural} {n_r} requests")
    print(f"  Silent villages (no requests): "
          f"{', '.join(r[0] for r in EXTRA_REGIONS[4:])}")
    if embeddings is None:
        print("  EMBEDDINGS MISSING — set GEMINI_API_KEY and re-run (task 2.5).")
        return 2
    if not scored:
        return 0
    return 0


# The impact-measurement example (enhancements D9): open drains in Paud,
# resolved RESOLVED_DAYS_AGO after a drainage facility was built. 40 complaints
# arrived in the 30 days before resolution, 5 in the 30 days after.
RESOLVED_DAYS_AGO = 35
SANITATION_TEXTS = [
    "Paud में नालियाँ भरी पड़ी हैं, गंदा पानी सड़क पर बह रहा है।",
    "Paud me gutter overflow ho raha hai, bahut badboo aati hai.",
    "Paud मध्ये गटार तुंबले आहे, डासांचा त्रास वाढला आहे.",
    "Paud की नाली हफ़्तों से साफ़ नहीं हुई, बीमारी फैलने का डर है।",
]


def seed_resolved_example(conn) -> None:
    """A resolved sanitation cluster with a real before/after history, a
    historical approval (logged in the decision chain) and a new facility."""
    from datetime import datetime, timedelta, timezone

    from app import audit
    from app.constants import CATEGORY_SANITATION
    from app.stages.fuse import fuse_cluster
    from app.stages.score import score_category

    print("Seeding the resolved Paud sanitation example (impact history) ...")
    now = datetime.now(timezone.utc)
    resolved_at = now - timedelta(days=RESOLVED_DAYS_AGO)
    paud = next(r for r in EXTRA_REGIONS if r[0] == "Paud")
    lat, lon = paud[1], paud[2]
    (ds_fac,) = conn.execute(
        "SELECT id FROM infrastructure_datasets WHERE name LIKE 'Synthetic water%'"
    ).fetchone()
    # One drainage facility long before, one built at resolution.
    for i, built in enumerate((now - timedelta(days=400), resolved_at)):
        flat, flon = jitter(lat, lon, 600)
        conn.execute(
            """INSERT INTO infrastructure_facilities
                 (dataset_id, facility_type, geom, functioning, name, created_at)
               VALUES (%s, 'sanitation_facility', ST_SetSRID(ST_MakePoint(%s,%s),4326),
                       true, %s, %s)""",
            (ds_fac, flon, flat, f"Paud Drainage Works {i + 1}", built))

    arrivals = ([resolved_at - timedelta(hours=HIST.uniform(1, 30 * 24)) for _ in range(40)]
                + [resolved_at + timedelta(hours=HIST.uniform(1, 30 * 24)) for _ in range(5)])
    texts = [SANITATION_TEXTS[i % len(SANITATION_TEXTS)] for i in range(len(arrivals))]
    embeddings = embed_texts(sorted(set(texts)))
    summary = "Open drains overflowing onto roads in Paud"
    (cluster_id,) = conn.execute(
        """INSERT INTO demand_clusters (category, centroid, representative_summary,
               member_count, status, confidence, created_at)
           VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), %s, %s, 'active',
                   'high', %s) RETURNING id""",
        (CATEGORY_SANITATION, lon, lat, summary, len(arrivals), min(arrivals)),
    ).fetchone()
    for i, (text, at) in enumerate(zip(texts, arrivals)):
        (cr,) = conn.execute(
            """INSERT INTO citizen_requests (channel, raw_text, submitter_ref, created_at)
               VALUES ('text', %s, %s, %s) RETURNING id""",
            (text, f"seed-sanit-paud-{i:04d}", at)).fetchone()
        (sr,) = conn.execute(
            """INSERT INTO structured_requests (citizen_request_id, category, urgency,
                   summary, detected_language, raw_location_mention)
               VALUES (%s, %s, 'medium', %s, %s, 'Paud') RETURNING id""",
            (cr, CATEGORY_SANITATION, summary,
             "Hinglish" if text.split()[1].isascii() else
             "Marathi" if "मध्ये" in text else "Hindi")).fetchone()
        plat, plon = jitter(lat, lon, 900)
        (gr,) = conn.execute(
            """INSERT INTO geocoded_requests (structured_request_id, geom, confidence,
                   embedding)
               VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), 'high', %s)
               RETURNING id""",
            (sr, plon, plat, embeddings.get(text) if embeddings else None)).fetchone()
        conn.execute(
            """INSERT INTO cluster_memberships (geocoded_request_id, demand_cluster_id,
                   similarity_score, created_at) VALUES (%s, %s, 0.93, %s)""",
            (gr, cluster_id, at))
    fuse_cluster(conn, cluster_id)
    score_category(conn, CATEGORY_SANITATION)

    # Historical recommendation, approval (in the hash chain) and resolution.
    (ind_id, ind_name, ind_value) = conn.execute(
        """SELECT id::text, name, value_text FROM priority_indicators
           WHERE demand_cluster_id = %s AND name = 'population affected'""",
        (cluster_id,)).fetchone()
    approved_at = resolved_at - timedelta(days=12)
    (rec_id,) = conn.execute(
        """INSERT INTO recommendations (demand_cluster_id, intervention_text,
               intervention_type, indicator_citations, status, created_at)
           VALUES (%s, %s, 'sanitation_infrastructure_evaluation', %s, 'published', %s)
           RETURNING id""",
        (cluster_id,
         "Rebuild the covered drain along Paud's main road and add a second "
         "drainage outfall, prioritising the stretch where overflow reaches homes.",
         json.dumps([{"indicator_id": ind_id, "name": ind_name, "value": ind_value}]),
         approved_at - timedelta(days=2))).fetchone()
    reviewer = "Demo Reviewer (seeded history)"
    conn.execute(
        """INSERT INTO approvals (recommendation_id, decision, reviewer, decided_at)
           VALUES (%s, 'approved', %s, %s)""", (rec_id, reviewer, approved_at))
    audit.append(conn, kind="publish_gate", subject_id=str(rec_id), decision="approved",
                 reviewer=reviewer, payload={"cluster_id": str(cluster_id),
                                             "seeded_history": True})
    conn.execute(
        """UPDATE demand_clusters SET status = 'resolved_unverified',
               resolved_at = %s, resolved_by = %s WHERE id = %s""",
        (resolved_at, reviewer, cluster_id))
    audit.append(conn, kind="mark_resolved", subject_id=str(cluster_id),
                 decision="resolved_unverified", reviewer=reviewer,
                 payload={"seeded_history": True})


def seed_enhancement_regions(cur, ds_pop, ds_fac) -> None:
    """Healthcare/road equity pairs, silent villages, named facilities
    (enhancements task 2.2). Runs after the water worked example so the
    original RNG sequence — and its cached embeddings — are unchanged."""
    print("Seeding healthcare/road pairs and silent villages ...")
    centres = {}
    for name, lat, lon, pop, inv, settlement, vuln, conn_idx in EXTRA_REGIONS:
        cur.execute(
            """INSERT INTO region_profiles
                 (name, boundary, centroid, population, investment_label,
                  dataset_id, settlement_type, vulnerability_index,
                  connectivity_index)
               VALUES (%s,
                 ST_Buffer(ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography, 2500)::geometry,
                 ST_SetSRID(ST_MakePoint(%s,%s),4326), %s, %s, %s, %s, %s, %s)""",
            (name, lon, lat, lon, lat, pop, inv, ds_pop, settlement, vuln, conn_idx),
        )
        centres[name] = {"lat": lat, "lon": lon}
    for place in ("Kothrud", "Velhe"):
        key = "region_a" if place == "Kothrud" else "region_b"
        centres[place] = LOCATIONS[key]

    for (place, ftype), count in EXTRA_FACILITIES.items():
        c = centres[place]
        for i in range(count):
            lat, lon = jitter(c["lat"], c["lon"], SERVICE_RADIUS_M * 0.8)
            cur.execute(
                """INSERT INTO infrastructure_facilities
                     (dataset_id, facility_type, geom, functioning, name)
                   VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s,%s),4326), true, %s)""",
                (ds_fac, ftype, lon, lat, f"{place} {FACILITY_LABEL[ftype]} {i + 1}"),
            )

    pair_reqs = []
    for category, urban, n_urban, rural, n_rural in EXTRA_PAIRS:
        for place, n in ((urban, n_urban), (rural, n_rural)):
            reqs = []
            for i in range(n):
                text = RNG.choice(CATEGORY_TEMPLATES[category]).format(place=place)
                lat, lon = jitter(centres[place]["lat"], centres[place]["lon"], 1200)
                reqs.append({
                    "text": text, "lat": lat, "lon": lon,
                    "submitter": f"seed-{category[:6]}-{place.lower()}-{i:04d}",
                    "language": ("Hinglish" if text[0].isascii() else
                                 "Marathi" if any(w in text for w in ("मध्ये", "मधला", "आहे"))
                                 else "Hindi"),
                })
            pair_reqs.append((category, place, reqs))

    embeddings = embed_texts([r["text"] for _, _, reqs in pair_reqs for r in reqs])
    for category, place, reqs in pair_reqs:
        summary = CATEGORY_SUMMARY[category].format(place=place)
        cur.execute(
            """INSERT INTO demand_clusters
                 (category, centroid, representative_summary, member_count,
                  status, confidence)
               VALUES (%s, ST_SetSRID(ST_MakePoint(%s,%s),4326), %s, %s, 'active', 'high')
               RETURNING id""",
            (category, centres[place]["lon"], centres[place]["lat"], summary, len(reqs)),
        )
        cluster_id = cur.fetchone()[0]
        for r in reqs:
            at = r.get("at") or arrival_time()
            cur.execute(
                """INSERT INTO citizen_requests
                     (channel, raw_text, submitter_ref, created_at)
                   VALUES ('text', %s, %s, %s) RETURNING id""",
                (r["text"], r["submitter"], at),
            )
            cr_id = cur.fetchone()[0]
            cur.execute(
                """INSERT INTO structured_requests
                     (citizen_request_id, category, urgency, summary,
                      detected_language, raw_location_mention)
                   VALUES (%s, %s, 'high', %s, %s, %s) RETURNING id""",
                (cr_id, category, summary, r["language"], place),
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
                     (geocoded_request_id, demand_cluster_id, similarity_score,
                      created_at)
                   VALUES (%s, %s, %s, %s)""",
                (gr_id, cluster_id, round(0.86 + RNG.random() * 0.1, 4), at),
            )


if __name__ == "__main__":
    sys.exit(main())
