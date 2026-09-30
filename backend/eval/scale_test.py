"""Clustering scale test (enhancements task 9.3, design D17).

    docker compose exec backend python -m eval.scale_test --n 10000

Generates N synthetic geocoded requests around the seeded cluster centroids
(plus some far-away ones that must found new clusters), with synthetic unit
embeddings near each cluster's own direction, and times the REAL Cluster
stage on every one. Everything runs in one transaction that is rolled back,
so the database is unchanged afterwards.

No external service is contacted: a socket guard allows connections to the
database only and fails the run on any other attempt.
"""
import argparse
import json
import math
import random
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.constants import EMBEDDING_DIM  # noqa: E402

RNG = random.Random(7)


class NetworkBlocked(RuntimeError):
    pass


def guard_network(allowed_host: str) -> list[str]:
    """Block every outbound connection except to the database host."""
    attempts: list[str] = []
    real_connect = socket.socket.connect
    allowed = {allowed_host, socket.gethostbyname(allowed_host)}

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in allowed and not str(host).startswith("/"):
            attempts.append(str(address))
            raise NetworkBlocked(f"scale test attempted a network call to {address}")
        return real_connect(self, address)

    socket.socket.connect = connect
    return attempts


def _unit(vec):
    n = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / n for v in vec]


def _near(base, noise=0.08):
    return _unit([b + RNG.gauss(0, noise / math.sqrt(EMBEDDING_DIM)) for b in base])


def run(n: int) -> dict:
    from app.stages import cluster

    with psycopg.connect(db.DATABASE_URL) as conn:
        centres = conn.execute(
            """SELECT dc.id::text, dc.category, ST_X(dc.centroid), ST_Y(dc.centroid),
                      (SELECT gr.embedding::text FROM cluster_memberships cm
                       JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
                       WHERE cm.demand_cluster_id = dc.id AND gr.embedding IS NOT NULL
                       LIMIT 1)
               FROM demand_clusters dc WHERE dc.centroid IS NOT NULL""").fetchall()
        centres = [(cid, cat, lon, lat, json.loads(e)) for cid, cat, lon, lat, e in centres if e]
        if not centres:
            raise SystemExit("seed the database first (seed.py)")
        prepared = []
        for i in range(n):
            _, cat, lon, lat, emb = RNG.choice(centres)
            far = i % 20 == 0  # 5% far away: must found new clusters
            dlon, dlat = ((RNG.uniform(0.3, 0.6), RNG.uniform(0.3, 0.6)) if far
                          else (RNG.gauss(0, 0.006), RNG.gauss(0, 0.006)))
            prepared.append((cat, lon + dlon, lat + dlat, _near(emb)))

        # Insert the synthetic requests (not timed: this is set-up).
        # structured_requests.citizen_request_id is UNIQUE: one citizen request
        # per synthetic row keeps the real schema contract.
        rows = []
        for cat, lon, lat, emb in prepared:
            (c_id,) = conn.execute(
                """INSERT INTO citizen_requests (channel, raw_text, submitter_ref)
                   VALUES ('text', 'scale test', 'scale-test') RETURNING id""").fetchone()
            (sr,) = conn.execute(
                """INSERT INTO structured_requests (citizen_request_id, category, urgency,
                       summary, detected_language, raw_location_mention)
                   VALUES (%s, %s, 'medium', 'scale', 'English', 'x') RETURNING id""",
                (c_id, cat)).fetchone()
            (gr,) = conn.execute(
                """INSERT INTO geocoded_requests (structured_request_id, geom, confidence,
                       embedding)
                   VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), 'high', %s::vector)
                   RETURNING id""", (sr, lon, lat, json.dumps(emb))).fetchone()
            rows.append(str(gr))

        clusters_before = conn.execute("SELECT count(*) FROM demand_clusters").fetchone()[0]
        start = time.perf_counter()
        joined = founded = 0
        for gr in rows:
            result = cluster.run(conn, gr, commit=False)
            if result["similarity"] is None:
                founded += 1
            else:
                joined += 1
        elapsed = time.perf_counter() - start
        clusters_after = conn.execute("SELECT count(*) FROM demand_clusters").fetchone()[0]
        conn.rollback()  # leave the database exactly as it was
    return {"requests": n, "seconds": round(elapsed, 2),
            "requests_per_second": round(n / elapsed, 1),
            "joined_existing": joined, "founded_new": founded,
            "clusters_created": clusters_after - clusters_before}


def main() -> int:
    ap = argparse.ArgumentParser(description="Setu clustering scale test")
    ap.add_argument("--n", type=int, default=10_000)
    args = ap.parse_args()
    attempts = guard_network(urlparse(db.DATABASE_URL).hostname or "localhost")
    out = run(args.n)
    out["external_network_calls"] = len(attempts)
    print(json.dumps(out, indent=2))
    return 0 if not attempts else 1


if __name__ == "__main__":
    sys.exit(main())
