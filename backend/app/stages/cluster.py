"""Cluster stage: GeocodedRequest → ClusterMembership (files/05 stage 3).

A request joins an existing DemandCluster only when ALL three conditions hold
(geospatial spec):
  1. same infrastructure category;
  2. semantic similarity > constants.CLUSTER_SIMILARITY_THRESHOLD — computed
     as the mean pgvector cosine similarity between the request embedding and
     the cluster members' embeddings;
  3. the request's point lies within constants.CLUSTER_PROXIMITY_M of the
     cluster centroid (PostGIS ST_DWithin on geography).

Otherwise a new DemandCluster is created with the request as founding member
(member_count 1, representative summary from the request). No request is ever
left unassigned. Ambiguity (several qualifying clusters) resolves to the
highest similarity; the losing candidates are returned in `alternatives` for
the caller to log in the RunTrace — the pipeline never blocks on it.

Documented posture for degraded requests (both covered by tests):
  - NULL geom (flagged geocode): the proximity condition cannot be verified,
    so the request founds a NEW single-member cluster carrying the flagged
    confidence and reason — it proceeds and stays queryable, it is never
    silently attached to a cluster whose location it may not share.
  - NULL embedding: the similarity condition is unsatisfiable, so the request
    likewise founds a new single-member cluster (flagged, reason recorded).

Cluster centroids are fixed at creation (the founding request's point); a
join bumps member_count and records the membership, it does not move the
centroid — deliberate for demo reproducibility.
"""
import psycopg

from app.constants import CLUSTER_PROXIMITY_M, CLUSTER_SIMILARITY_THRESHOLD


def _candidates(conn: psycopg.Connection, geocoded_request_id: str,
                category: str) -> list[tuple[str, float]]:
    """Qualifying (cluster_id, similarity) pairs, best similarity first.

    All three membership conditions are applied here; members without an
    embedding are ignored in the similarity mean (a cluster whose members are
    all embedding-less can never be joined by similarity).
    """
    rows = conn.execute(
        """
        WITH req AS (
            SELECT geom, embedding FROM geocoded_requests WHERE id = %(gr)s
        )
        SELECT c.id::text,
               AVG(1 - (g.embedding <=> (SELECT embedding FROM req)))::float8
                 AS similarity
        FROM demand_clusters c
        JOIN cluster_memberships m ON m.demand_cluster_id = c.id
        JOIN geocoded_requests g ON g.id = m.geocoded_request_id
        WHERE c.category = %(cat)s
          AND c.centroid IS NOT NULL
          AND g.embedding IS NOT NULL
          AND ST_DWithin(c.centroid::geography,
                         (SELECT geom FROM req)::geography, %(prox)s)
        GROUP BY c.id
        HAVING AVG(1 - (g.embedding <=> (SELECT embedding FROM req))) > %(thr)s
        ORDER BY similarity DESC
        """,
        {"gr": geocoded_request_id, "cat": category,
         "prox": CLUSTER_PROXIMITY_M, "thr": CLUSTER_SIMILARITY_THRESHOLD},
    ).fetchall()
    return [(cid, float(sim)) for cid, sim in rows]


def _new_cluster(conn: psycopg.Connection, geocoded_request_id: str,
                 category: str, summary: str, confidence: str,
                 reason: str | None, commit: bool = True) -> dict:
    """Found a new single-member DemandCluster (unmatched-request posture)."""
    c = conn.execute(
        """INSERT INTO demand_clusters
             (category, centroid, representative_summary, member_count,
              status, confidence, confidence_reason)
           SELECT %s, g.geom, %s, 1, 'active', %s, %s
           FROM geocoded_requests g WHERE g.id = %s
           RETURNING id""",
        (category, summary, confidence, reason, geocoded_request_id),
    ).fetchone()
    cluster_id = str(c[0])
    m = conn.execute(
        """INSERT INTO cluster_memberships
             (geocoded_request_id, demand_cluster_id, similarity_score)
           VALUES (%s, %s, NULL) RETURNING id""",
        (geocoded_request_id, cluster_id),
    ).fetchone()
    if commit:
        conn.commit()
    return {"cluster_id": cluster_id, "membership_id": str(m[0]),
            "similarity": None, "alternatives": []}


def run(conn: psycopg.Connection, geocoded_request_id: str, *,
        commit: bool = True) -> dict:
    """Assign the request to a DemandCluster; never leaves it unassigned.

    commit=False lets a caller make re-assignment atomic with its own
    changes (the location follow-up's relocate, enhancements D8).

    Returns {cluster_id, membership_id, similarity, alternatives:
    [{cluster_id, similarity}]} — the caller logs `alternatives` in the
    RunTrace (geospatial spec's ambiguity requirement).
    """
    row = conn.execute(
        """SELECT sr.category, sr.summary, gr.confidence,
                  gr.confidence_reason, gr.geom IS NULL, gr.embedding IS NULL
           FROM geocoded_requests gr
           JOIN structured_requests sr ON sr.id = gr.structured_request_id
           WHERE gr.id = %s""",
        (geocoded_request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown geocoded_request {geocoded_request_id}")
    category, summary, confidence, reason, geom_null, embedding_null = row

    if geom_null or embedding_null:
        # Degraded request (see module docstring): proceed as its own
        # flagged single-member cluster — never dropped, never mis-attached.
        why = ("no resolved coordinates" if geom_null else "no embedding")
        return _new_cluster(
            conn, geocoded_request_id, category, summary, "flagged",
            reason or f"clustered alone: {why} for membership checks",
            commit=commit,
        )

    candidates = _candidates(conn, geocoded_request_id, category)
    if not candidates:
        return _new_cluster(conn, geocoded_request_id, category, summary,
                            confidence, reason, commit=commit)

    # Ambiguity → highest similarity wins; the rest are logged alternatives.
    (winner_id, winner_sim), rest = candidates[0], candidates[1:]
    m = conn.execute(
        """INSERT INTO cluster_memberships
             (geocoded_request_id, demand_cluster_id, similarity_score)
           VALUES (%s, %s, %s) RETURNING id""",
        (geocoded_request_id, winner_id, round(winner_sim, 6)),
    ).fetchone()
    conn.execute(
        "UPDATE demand_clusters SET member_count = member_count + 1 WHERE id = %s",
        (winner_id,),
    )
    if commit:
        conn.commit()
    return {
        "cluster_id": winner_id,
        "membership_id": str(m[0]),
        "similarity": winner_sim,
        "alternatives": [
            {"cluster_id": cid, "similarity": sim} for cid, sim in rest
        ],
    }
