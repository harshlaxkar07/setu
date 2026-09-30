"""Citizen intake API (design D4): persist-first ingestion + status polling.

- POST /api/requests/voice  (multipart: audio + conversation_id)
- POST /api/requests/text   (json: text + conversation_id)
- GET  /api/requests/{id}/status → {status, receipt|null}

Ingestion never waits on the pipeline: the CitizenRequest row (and raw audio
on the media volume) is persisted FIRST, then the pipeline is kicked as a
background task — a downstream failure can never lose the raw request
(citizen-intake spec "persisted before processing and is immutable").

Pipeline kick: if `app.pipeline` exists (the §7 LangGraph graph), its
run_pipeline(citizen_request_id) is called; until then a fallback runs
Understand → Locate → Cluster inline with traced_stage entries, so Track A is
demonstrable stand-alone and §7 swaps in the graph by adding one module.

There is deliberately NO update or delete endpoint for citizen requests —
immutability is also enforced by a DB trigger.
"""
import importlib.util
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import db
from app.gemini import GeminiUnavailable
from app.stages import cluster, locate, understand
from app.trace import create_run_trace, set_status, traced_stage

router = APIRouter(prefix="/api/requests", tags=["citizen-intake"])

MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", "/media"))

# Upload guardrails: press-and-hold voice notes are seconds long, not files.
MAX_AUDIO_BYTES = 15 * 1024 * 1024


class TextSubmission(BaseModel):
    """Text-fallback payload. conversation_id is the client-generated UUID —
    the stable pseudonymous submitter reference (no name/phone, ever)."""

    text: str = Field(min_length=1, max_length=4000)
    conversation_id: str = Field(min_length=8, max_length=64)


def _run_fallback(citizen_request_id: str) -> None:
    """Inline Understand → Locate → Cluster with RunTrace entries.

    Failure posture: any stage failure marks the trace `needs_retry` and stops
    — the raw CitizenRequest is untouched and remains reprocessable. Stage
    functions are called through their modules so tests can monkeypatch them.
    """
    with db.pool.connection() as conn:
        trace_id = create_run_trace(conn, citizen_request_id)
        try:
            with traced_stage(conn, trace_id, "Understand",
                              input_ref=citizen_request_id) as entry:
                sr_id = understand.run(conn, citizen_request_id)
                entry["output_ref"] = sr_id
            with traced_stage(conn, trace_id, "Locate", input_ref=sr_id) as entry:
                gr_id = locate.run(conn, sr_id)
                entry["output_ref"] = gr_id
            with traced_stage(conn, trace_id, "Cluster", input_ref=gr_id) as entry:
                result = cluster.run(conn, gr_id)
                entry["output_ref"] = result["cluster_id"]
                entry["similarity"] = result["similarity"]
                entry["alternatives"] = result["alternatives"]
            # Later stages (Fuse → Score → Recommend → Gate) belong to the §7
            # graph; the fallback leaves the run in_progress after Cluster.
        except GeminiUnavailable:
            conn.rollback()
            set_status(conn, trace_id, "needs_retry")
        except Exception:
            conn.rollback()
            set_status(conn, trace_id, "needs_retry")


def _kick_pipeline(citizen_request_id: str) -> None:
    """Run the real LangGraph pipeline when present, else the inline fallback."""
    if importlib.util.find_spec("app.pipeline") is not None:
        from app.pipeline import run_pipeline  # provided by §7

        run_pipeline(citizen_request_id)
        return
    _run_fallback(citizen_request_id)


def _insert_request(channel: str, conversation_id: str,
                    raw_text: str | None = None,
                    audio_path: str | None = None) -> str:
    with db.pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO citizen_requests
                 (channel, raw_text, audio_path, submitter_ref)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (channel, raw_text, audio_path, conversation_id),
        ).fetchone()
        conn.commit()
        return str(row[0])


@router.post("/voice", status_code=201)
async def submit_voice(background_tasks: BackgroundTasks, audio: UploadFile,
                       conversation_id: str = Form(..., min_length=8,
                                                   max_length=64)) -> dict:
    """Voice submission: audio to the media volume + CitizenRequest row FIRST,
    pipeline kicked afterwards as a background task (design D4)."""
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio upload")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio upload too large")

    suffix = Path(audio.filename or "note.webm").suffix or ".webm"
    audio_path = MEDIA_DIR / f"{uuid.uuid4()}{suffix}"
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(data)  # raw payload persisted before the row

    cr_id = _insert_request("voice", conversation_id, audio_path=str(audio_path))
    background_tasks.add_task(_kick_pipeline, cr_id)
    return {"id": cr_id, "status": "received"}


@router.post("/text", status_code=201)
async def submit_text(body: TextSubmission,
                      background_tasks: BackgroundTasks) -> dict:
    """Text-fallback submission: persist first, then kick the pipeline."""
    cr_id = _insert_request("text", body.conversation_id, raw_text=body.text)
    background_tasks.add_task(_kick_pipeline, cr_id)
    return {"id": cr_id, "status": "received"}


@router.get("/{request_id}/status")
def request_status(request_id: str) -> dict:
    """Polling endpoint for the receipt bubble (design D4 step 4).

    status: latest RunTrace status, or "received" before any trace exists.
    receipt: the understood extraction once Understand has completed, else
    null — the page renders it with the AI-drafted provenance marker.
    """
    try:
        uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown request")

    with db.pool.connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM citizen_requests WHERE id = %s", (request_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="unknown request")

        trace = conn.execute(
            """SELECT status FROM run_traces WHERE citizen_request_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            (request_id,),
        ).fetchone()
        sr = conn.execute(
            """SELECT category, urgency, summary, detected_language
               FROM structured_requests WHERE citizen_request_id = %s""",
            (request_id,),
        ).fetchone()

        # §8: the verification prompt rides this same poll (design D4 step 5)
        # — every RESOLVED cluster this conversation contributed to. The key
        # is present only when there is at least one, so the pre-§8 payload
        # shape (and its exact-equality tests) is unchanged otherwise.
        prompts = conn.execute(
            """SELECT DISTINCT dc.id::text, dc.category,
                      dc.representative_summary, dc.status::text, dc.created_at
               FROM demand_clusters dc
               JOIN cluster_memberships cm ON cm.demand_cluster_id = dc.id
               JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
               JOIN structured_requests sr ON sr.id = gr.structured_request_id
               JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
               WHERE cr.submitter_ref = (SELECT submitter_ref
                                         FROM citizen_requests WHERE id = %s)
                 AND dc.status IN ('resolved_unverified', 'resolved_verified')
               ORDER BY dc.created_at""",
            (request_id,),
        ).fetchall()

    receipt = None
    if sr is not None:
        receipt = {"category": sr[0], "urgency": sr[1], "summary": sr[2],
                   "detected_language": sr[3]}
    payload = {"status": trace[0] if trace else "received", "receipt": receipt}
    # Location follow-up (enhancements D8): the chat asks once when true.
    from app import relocate
    with db.pool.connection() as conn:
        if relocate.needs_location(conn, request_id):
            payload["needs_location"] = True
    if prompts:
        payload["verification_prompts"] = [
            {"cluster_id": p[0], "category": p[1], "summary": p[2],
             "status": p[3]}
            for p in prompts
        ]
    return payload


@router.get("/{request_id}/timeline")
def request_timeline(request_id: str) -> dict:
    """Stage-by-stage progress for the citizen (enhancements D11)."""
    from app import timeline
    try:
        uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown request")
    with db.pool.connection() as conn:
        out = timeline.build(conn, request_id)
    if out is None:
        raise HTTPException(status_code=404, detail="unknown request")
    return out


class LocationAnswer(BaseModel):
    """The citizen's answer to "which village, ward or landmark?"."""

    answer: str = Field(min_length=2, max_length=200)
    conversation_id: str = Field(min_length=8, max_length=64)


@router.post("/{request_id}/location")
def answer_location(request_id: str, body: LocationAnswer) -> dict:
    """Attach the follow-up answer to the SAME request and re-locate it
    (enhancements D8). Only the conversation that submitted it may answer."""
    from app import relocate
    try:
        uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="unknown request")
    with db.pool.connection() as conn:
        owner = conn.execute(
            "SELECT submitter_ref FROM citizen_requests WHERE id = %s",
            (request_id,)).fetchone()
    if owner is None or owner[0] != body.conversation_id:
        raise HTTPException(status_code=404, detail="unknown request")
    try:
        return relocate.relocate(request_id, body.answer.strip())
    except relocate.NotEligible as exc:
        raise HTTPException(status_code=409, detail=str(exc))
