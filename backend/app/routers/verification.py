"""§8 verification bolt-on API.

- POST /api/verification/{cluster_id}       citizen follow-up (multipart:
  photos and/or voice + conversation_id) for a RESOLVED cluster only
- GET  /api/verifications[?flagged=true]    review listing (dashboard) —
  pseudonymous, cluster-scoped, with the ORIGINAL complaint summary for
  side-by-side comparison
- POST /api/verifications/{record_id}/review  human review decision — the
  ONLY path that clears a flag

Posture mirrors intake (design D4): the raw follow-up media is persisted
FIRST (immutably — there is deliberately no update/delete endpoint for
verification media), the VerificationRecord starts result='pending', and the
plausibility check is kicked as a background task. The submitter is the
pseudonymous conversation_id; it is stored for prompt routing but NEVER
exposed through any policymaker-facing response here.
"""
import json
import os
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     HTTPException, UploadFile)
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app import audit, auth, db
from app.stages import verify as verify_stage
from app.stages.verify import RESOLVED_STATES

router = APIRouter(prefix="/api", tags=["verification"])

MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "/media"))

# Upload guardrails: phone photos and press-and-hold voice notes, not files.
MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_VOICE_BYTES = 15 * 1024 * 1024
MAX_PHOTOS = 6


def _kick_verification(record_id: str) -> None:
    """Background plausibility check (module-level so tests can silence it)."""
    verify_stage.run_verification(record_id)


def _require_resolved_cluster(conn, cluster_id: str) -> None:
    row = conn.execute(
        "SELECT status::text FROM demand_clusters WHERE id = %s", (cluster_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="cluster not found")
    if row[0] not in RESOLVED_STATES:
        raise HTTPException(
            status_code=409,
            detail=f"cluster is '{row[0]}' — follow-ups are accepted only for "
                   "a cluster that has been marked resolved",
        )


@router.post("/verification/{cluster_id}", status_code=201)
async def submit_followup(
    cluster_id: str,
    background_tasks: BackgroundTasks,
    photos: list[UploadFile] = File(default=[]),
    voice: UploadFile | None = File(default=None),
    conversation_id: str = Form(..., min_length=8, max_length=64),
) -> dict:
    """Citizen follow-up for a resolved cluster (verification spec).

    Media is stored immutably under MEDIA_DIR/verification, the record starts
    pending, and the plausibility check runs autonomously afterwards — the
    upload response never waits on Gemini.
    """
    try:
        uuid.UUID(cluster_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="cluster not found")

    if len(photos) > MAX_PHOTOS:
        raise HTTPException(status_code=413, detail="too many photos")

    photo_payloads: list[tuple[bytes, str]] = []
    for photo in photos:
        data = await photo.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty photo upload")
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="photo upload too large")
        suffix = Path(photo.filename or "photo.jpg").suffix or ".jpg"
        photo_payloads.append((data, suffix))

    voice_payload: tuple[bytes, str] | None = None
    if voice is not None:
        data = await voice.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty voice upload")
        if len(data) > MAX_VOICE_BYTES:
            raise HTTPException(status_code=413, detail="voice upload too large")
        suffix = Path(voice.filename or "followup.webm").suffix or ".webm"
        voice_payload = (data, suffix)

    if not photo_payloads and voice_payload is None:
        raise HTTPException(status_code=400,
                            detail="a follow-up needs a photo or a voice note")

    with db.pool.connection() as conn:
        _require_resolved_cluster(conn, cluster_id)

        # Raw media persisted FIRST, immutably — no API path ever rewrites
        # these files or the paths recorded below (verification spec).
        target_dir = MEDIA_DIR / "verification"
        target_dir.mkdir(parents=True, exist_ok=True)
        media_paths: list[str] = []
        for data, suffix in photo_payloads:
            path = target_dir / f"{uuid.uuid4()}{suffix}"
            path.write_bytes(data)
            media_paths.append(str(path))
        voice_path: str | None = None
        if voice_payload is not None:
            data, suffix = voice_payload
            vp = target_dir / f"{uuid.uuid4()}{suffix}"
            vp.write_bytes(data)
            voice_path = str(vp)

        row = conn.execute(
            """INSERT INTO verification_records
                 (demand_cluster_id, media_paths, voice_path, submitter_ref)
               VALUES (%s, %s::jsonb, %s, %s) RETURNING id""",
            (cluster_id, json.dumps(media_paths), voice_path, conversation_id),
        ).fetchone()
        conn.commit()
        record_id = str(row[0])

    # Autonomous plausibility check — same async kick as intake (design D4).
    background_tasks.add_task(_kick_verification, record_id)
    return {"id": record_id, "demand_cluster_id": cluster_id,
            "result": "pending"}


@router.get("/verifications")
def list_verifications(flagged: bool | None = None) -> list[dict[str, Any]]:
    """VerificationRecords for the review surface (dashboard, design D6).

    Cluster-scoped and pseudonymous: the ORIGINAL complaint summary rides
    along for side-by-side comparison, and NO submitter identity — not even
    the pseudonymous submitter_ref — is exposed policymaker-side.
    """
    q = """
        SELECT vr.id::text, vr.demand_cluster_id::text,
               dc.representative_summary AS cluster_summary,
               dc.status::text AS cluster_status,
               vr.media_paths, vr.voice_path, vr.result::text, vr.flagged,
               vr.review_decision, vr.review_reviewer, vr.reviewed_at,
               vr.created_at
        FROM verification_records vr
        JOIN demand_clusters dc ON dc.id = vr.demand_cluster_id
    """
    params: tuple = ()
    if flagged is not None:
        q += " WHERE vr.flagged = %s"
        params = (flagged,)
    q += " ORDER BY vr.created_at DESC"
    with db.pool.connection() as conn:
        rows = conn.cursor(row_factory=dict_row).execute(q, params).fetchall()
    return [
        {
            "id": r["id"],
            "demand_cluster_id": r["demand_cluster_id"],
            "cluster_summary": r["cluster_summary"],
            "cluster_status": r["cluster_status"],
            "media_paths": r["media_paths"],
            "voice_path": r["voice_path"],
            "result": r["result"],
            "flagged": r["flagged"],
            "review_decision": r["review_decision"],
            "review_reviewer": r["review_reviewer"],
            "reviewed_at": r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


class ReviewBody(BaseModel):
    decision: Literal["confirm_resolved", "reject_resolution"]
    reviewer: str | None = Field(default=None, max_length=200)  # ignored (D15)


@router.post("/verifications/{record_id}/review")
def review_verification(record_id: str, body: ReviewBody,
                        reviewer: str = Depends(auth.require_reviewer)) -> dict[str, Any]:
    """Record the human review decision — the only path that resolves a flag.

    confirm_resolved → cluster becomes resolved_verified;
    reject_resolution → cluster STAYS resolved_unverified.
    Either way the decision + reviewer + timestamp are recorded and the flag
    is resolved (the spec's "flag persists until a human records a review
    decision"). One decision per record: a second review is refused, so the
    recorded decision stays retrievable and unrewritten.
    """
    try:
        uuid.UUID(record_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="verification record not found")

    with db.pool.connection() as conn:
        # Atomic check-and-record: only a not-yet-reviewed record.
        updated = conn.execute(
            """UPDATE verification_records
               SET review_decision = %s, review_reviewer = %s,
                   reviewed_at = now(), flagged = false
               WHERE id = %s AND reviewed_at IS NULL
               RETURNING demand_cluster_id::text, reviewed_at""",
            (body.decision, reviewer, record_id),
        ).fetchone()
        if updated is None:
            exists = conn.execute(
                "SELECT 1 FROM verification_records WHERE id = %s", (record_id,)
            ).fetchone()
            conn.rollback()
            if exists is None:
                raise HTTPException(status_code=404,
                                    detail="verification record not found")
            raise HTTPException(status_code=409,
                                detail="a review decision is already recorded "
                                       "for this record")
        cluster_id, reviewed_at = updated

        if body.decision == "confirm_resolved":
            conn.execute(
                """UPDATE demand_clusters SET status = 'resolved_verified'
                   WHERE id = %s AND status = ANY(%s)""",
                (cluster_id, list(RESOLVED_STATES)),
            )
        # reject_resolution: the cluster stays resolved_unverified — a
        # rejected resolution claim is not verified, and nothing is deleted.
        audit.append(conn, kind="verification_review", subject_id=record_id,
                     decision=body.decision, reviewer=reviewer,
                     payload={"cluster_id": cluster_id})
        conn.commit()

        cluster_status = conn.execute(
            "SELECT status::text FROM demand_clusters WHERE id = %s",
            (cluster_id,),
        ).fetchone()[0]

    return {
        "id": record_id,
        "demand_cluster_id": cluster_id,
        "decision": body.decision,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at.isoformat(),
        "flagged": False,
        "cluster_status": cluster_status,
    }
