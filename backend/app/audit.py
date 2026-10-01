"""Hash-chained decision log (enhancements design D14).

`append` is called inside the transaction that records a human decision, so
the decision and its log entry commit (or roll back) together. Appends are
serialised with a transaction-scoped advisory lock, so concurrent decisions
still form one linear chain.

    hash = sha256(canonical JSON of the entry without its hash + prev_hash)

`verify` recomputes every hash in order and reports the first entry whose
content or link no longer matches.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import psycopg

GENESIS = "0" * 64
_LOCK_KEY = 0x6C6F67  # "log"


def _entry_hash(kind: str, subject_id: str, decision: str, reviewer: str,
                decided_at: str, payload: Any, prev_hash: str) -> str:
    body = json.dumps(
        {"kind": kind, "subject_id": subject_id, "decision": decision,
         "reviewer": reviewer, "decided_at": decided_at, "payload": payload},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    )
    return hashlib.sha256((body + prev_hash).encode()).hexdigest()


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat(timespec="microseconds")


def append(conn: psycopg.Connection, *, kind: str, subject_id: str,
           decision: str, reviewer: str, payload: dict | None = None) -> str:
    """Append one decision; returns its hash. Does not commit."""
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
    row = conn.execute(
        "SELECT hash FROM decision_log ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = row[0] if row else GENESIS
    decided_at = datetime.now(timezone.utc)
    payload = payload or {}
    digest = _entry_hash(kind, str(subject_id), decision, reviewer,
                         _iso(decided_at), payload, prev_hash)
    conn.execute(
        """INSERT INTO decision_log
             (kind, subject_id, decision, reviewer, decided_at, payload,
              prev_hash, hash)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (kind, str(subject_id), decision, reviewer, decided_at,
         json.dumps(payload, default=str), prev_hash, digest),
    )
    return digest


def verify(conn: psycopg.Connection) -> dict[str, Any]:
    """{intact, entries, first_break: {seq, reason} | None}."""
    prev = GENESIS
    count = 0
    for (seq, kind, subject_id, decision, reviewer, decided_at, payload,
         prev_hash, digest) in conn.execute(
            """SELECT seq, kind, subject_id, decision, reviewer, decided_at,
                      payload, prev_hash, hash FROM decision_log ORDER BY seq"""):
        count += 1
        if prev_hash != prev:
            return {"intact": False, "entries": count,
                    "first_break": {"seq": seq, "reason": "link to previous entry broken "
                                    "(an entry was removed or reordered)"}}
        expected = _entry_hash(kind, subject_id, decision, reviewer,
                               _iso(decided_at), payload, prev_hash)
        if expected != digest:
            return {"intact": False, "entries": count,
                    "first_break": {"seq": seq, "reason": "entry content does not "
                                    "match its hash (edited after recording)"}}
        prev = digest
    return {"intact": True, "entries": count, "first_break": None}
