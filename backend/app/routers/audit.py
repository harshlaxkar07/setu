"""Decision-log audit endpoints (enhancements design D14). Read-only."""
from typing import Any

from fastapi import APIRouter
from psycopg.rows import dict_row

from app import audit, db

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/verify")
def verify_chain() -> dict[str, Any]:
    with db.pool.connection() as conn:
        return audit.verify(conn)


@router.get("/log")
def recent(limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    with db.pool.connection() as conn:
        return conn.cursor(row_factory=dict_row).execute(
            """SELECT seq, kind, subject_id, decision, reviewer, decided_at,
                      payload, hash FROM decision_log
               ORDER BY seq DESC LIMIT %s""", (limit,)).fetchall()
