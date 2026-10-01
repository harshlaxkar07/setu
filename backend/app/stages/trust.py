"""Trust stage: anti-manipulation checks after Cluster (enhancements D2).

Three rules, each writing a `trust_flags` row with a human-readable reason:

  duplicate_burst  near-identical texts piling into one cluster within minutes
  repeat_source    one pseudonymous conversation id flooding one cluster
  cluster_spike    a cluster's arrivals far above its own baseline rate

Flags never delete or hide anything (governing principle 3). Request-level
flags take the request out of the complaint-volume indicator while open or
confirmed (score.counted_volume); a reviewer can clear them. A spike lowers
the cluster's confidence and states why.
"""
import re
import unicodedata

import psycopg

from app.constants import (
    TRUST_BASELINE_DAYS,
    TRUST_BURST_MIN_MATCHES,
    TRUST_BURST_WINDOW_S,
    TRUST_REPEAT_LIMIT,
    TRUST_REPEAT_WINDOW_S,
    TRUST_SIMILARITY,
    TRUST_SPIKE_MIN_ARRIVALS,
    TRUST_SPIKE_MULTIPLE,
    TRUST_SPIKE_WINDOW_S,
)

REQUEST_RULES = ("duplicate_burst", "repeat_source")


def normalise(text: str | None) -> str:
    """Case/punctuation/whitespace-insensitive form for exact-duplicate checks."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[\W_]+", " ", text)
    return " ".join(text.split())


def _duration(seconds: int) -> str:
    if seconds % 3600 == 0:
        h = seconds // 3600
        return f"{h} hour" + ("s" if h != 1 else "")
    return f"{seconds // 60} minutes"


def _flag_request(conn, citizen_request_id: str, cluster_id: str,
                  rule: str, reason: str) -> dict | None:
    row = conn.execute(
        """INSERT INTO trust_flags (citizen_request_id, demand_cluster_id, rule, reason)
           VALUES (%s, %s, %s, %s)
           ON CONFLICT (citizen_request_id, rule)
               WHERE citizen_request_id IS NOT NULL DO NOTHING
           RETURNING id""",
        (citizen_request_id, cluster_id, rule, reason),
    ).fetchone()
    return {"id": str(row[0]), "rule": rule, "reason": reason} if row else None


def _duplicate_burst(conn, me: dict, cluster_id: str) -> dict | None:
    rows = conn.execute(
        """SELECT COALESCE(cr.raw_text, t.text),
                  CASE WHEN gr.embedding IS NULL OR %(emb)s::vector IS NULL THEN NULL
                       ELSE 1 - (gr.embedding <=> %(emb)s::vector) END
           FROM cluster_memberships cm
           JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
           JOIN structured_requests sr ON sr.id = gr.structured_request_id
           JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
           LEFT JOIN LATERAL (SELECT text FROM transcriptions
                              WHERE citizen_request_id = cr.id
                              ORDER BY created_at DESC LIMIT 1) t ON true
           WHERE cm.demand_cluster_id = %(cluster)s
             AND cr.id <> %(me)s
             AND cr.created_at <= %(at)s
             AND cr.created_at > %(at)s - make_interval(secs => %(window)s)""",
        {"emb": me["embedding"], "cluster": cluster_id, "me": me["id"],
         "at": me["created_at"], "window": TRUST_BURST_WINDOW_S},
    ).fetchall()
    mine = normalise(me["text"])
    matches = sum(
        1 for text, sim in rows
        if (mine and normalise(text) == mine)
        or (sim is not None and float(sim) >= TRUST_SIMILARITY)
    )
    if matches < TRUST_BURST_MIN_MATCHES:
        return None
    return _flag_request(
        conn, me["id"], cluster_id, "duplicate_burst",
        f"duplicate burst: {matches} near-identical requests joined this cluster "
        f"in the {_duration(TRUST_BURST_WINDOW_S)} before this one",
    )


def _repeat_source(conn, me: dict, cluster_id: str) -> dict | None:
    if not me["submitter"]:
        return None
    (count,) = conn.execute(
        """SELECT count(*) FROM cluster_memberships cm
           JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
           JOIN structured_requests sr ON sr.id = gr.structured_request_id
           JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
           WHERE cm.demand_cluster_id = %(cluster)s
             AND cr.submitter_ref = %(who)s
             AND cr.created_at <= %(at)s
             AND cr.created_at > %(at)s - make_interval(secs => %(window)s)""",
        {"cluster": cluster_id, "who": me["submitter"], "at": me["created_at"],
         "window": TRUST_REPEAT_WINDOW_S},
    ).fetchone()
    if count <= TRUST_REPEAT_LIMIT:
        return None
    return _flag_request(
        conn, me["id"], cluster_id, "repeat_source",
        f"repeat source: {count} submissions in {_duration(TRUST_REPEAT_WINDOW_S)} "
        "from one source",
    )


def check_cluster_spike(conn: psycopg.Connection, cluster_id: str) -> dict | None:
    """Flag the cluster (once while open) and lower its confidence on a spike."""
    recent, before, span_h = conn.execute(
        """SELECT count(*) FILTER (WHERE cm.created_at > now() - make_interval(secs => %(w)s)),
                  count(*) FILTER (WHERE cm.created_at <= now() - make_interval(secs => %(w)s)
                                     AND cm.created_at > now() - make_interval(days => %(d)s)),
                  GREATEST(EXTRACT(EPOCH FROM (
                      now() - make_interval(secs => %(w)s)
                      - GREATEST(min(cm.created_at), now() - make_interval(days => %(d)s))
                  )) / 3600.0, 1.0)
           FROM cluster_memberships cm WHERE cm.demand_cluster_id = %(c)s""",
        {"w": TRUST_SPIKE_WINDOW_S, "d": TRUST_BASELINE_DAYS, "c": cluster_id},
    ).fetchone()
    window_h = TRUST_SPIKE_WINDOW_S / 3600.0
    baseline = float(before) / float(span_h) * window_h  # expected per window
    if recent < TRUST_SPIKE_MIN_ARRIVALS or recent <= TRUST_SPIKE_MULTIPLE * baseline:
        return None
    already = conn.execute(
        """SELECT 1 FROM trust_flags WHERE demand_cluster_id = %s
             AND rule = 'cluster_spike' AND status = 'open'""",
        (cluster_id,),
    ).fetchone()
    reason = (
        f"cluster spike: {recent} new members in the last "
        f"{_duration(TRUST_SPIKE_WINDOW_S)} vs a baseline of {baseline:.1f} per "
        f"{_duration(TRUST_SPIKE_WINDOW_S)} over the previous {TRUST_BASELINE_DAYS} days"
    )
    conn.execute(
        """UPDATE demand_clusters SET confidence = 'medium', confidence_reason = %s
           WHERE id = %s AND confidence = 'high'""",
        (reason, cluster_id),
    )
    if already:
        return None
    (flag_id,) = conn.execute(
        """INSERT INTO trust_flags (demand_cluster_id, rule, reason)
           VALUES (%s, 'cluster_spike', %s) RETURNING id""",
        (cluster_id, reason),
    ).fetchone()
    return {"id": str(flag_id), "rule": "cluster_spike", "reason": reason}


def run(conn: psycopg.Connection, geocoded_request_id: str, cluster_id: str) -> list[dict]:
    """Evaluate every rule for one newly clustered request; returns new flags.
    Commits (a Track A-style stage: its flags must survive a later failure)."""
    row = conn.execute(
        """SELECT cr.id, COALESCE(cr.raw_text, t.text), cr.submitter_ref,
                  cr.created_at, gr.embedding::text
           FROM geocoded_requests gr
           JOIN structured_requests sr ON sr.id = gr.structured_request_id
           JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
           LEFT JOIN LATERAL (SELECT text FROM transcriptions
                              WHERE citizen_request_id = cr.id
                              ORDER BY created_at DESC LIMIT 1) t ON true
           WHERE gr.id = %s""",
        (geocoded_request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown geocoded_request {geocoded_request_id}")
    me = {"id": str(row[0]), "text": row[1], "submitter": row[2],
          "created_at": row[3], "embedding": row[4]}
    flags = [f for f in (
        _duplicate_burst(conn, me, cluster_id),
        _repeat_source(conn, me, cluster_id),
        check_cluster_spike(conn, cluster_id),
    ) if f]
    conn.commit()
    return flags


def counted_volume(conn: psycopg.Connection, cluster_id: str) -> int:
    """The cluster's member count minus members excluded by an open/confirmed
    request-level trust flag (member_count stays the authoritative total)."""
    (total, excluded) = conn.execute(
        """SELECT dc.member_count,
                  (SELECT count(DISTINCT sr.citizen_request_id)
                   FROM cluster_memberships cm
                   JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
                   JOIN structured_requests sr ON sr.id = gr.structured_request_id
                   JOIN trust_flags tf ON tf.citizen_request_id = sr.citizen_request_id
                   WHERE cm.demand_cluster_id = dc.id
                     AND tf.rule = ANY(%s) AND tf.status IN ('open', 'confirmed'))
           FROM demand_clusters dc WHERE dc.id = %s""",
        (list(REQUEST_RULES), cluster_id),
    ).fetchone()
    return max(int(total) - int(excluded), 0)
