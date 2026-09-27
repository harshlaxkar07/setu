"""Verify stage (§8, stage 8 of the pipeline): post-resolution plausibility.

Runs autonomously (no gate) right after a follow-up submission is persisted
(pipeline-orchestration spec "Verify stage runs autonomously post-resolution").
The submission is compared against the resolved cluster's ORIGINAL complaint
(representative_summary):

- photos            → Gemini 2.5 Flash vision (`call_gemini(..., image_bytes=)`)
- voice note only   → local Faster-Whisper transcription (app.stt — audio
                      never leaves the host), transcript compared via Gemini
- photos + voice    → vision path, transcript included as added context

Outcome routing (verification spec):

- match              → record confirmed, cluster ConfidenceLevel untouched
                       (stays high), cluster → resolved_verified
- mismatch /
  needs_human_review → record flagged for human review; the cluster STAYS
                       resolved_unverified; NO automated path clears the flag
- check failure      → call_gemini already retried once; a second failure
  (GeminiUnavailable, or a local STT/file error) records the result as
  needs_human_review + flagged. A failure NEVER yields match, never drops
  the submission, never auto-closes the cluster.

Every execution is recorded as a RunTrace with a "Verify" stage entry.
run_traces.citizen_request_id is NOT NULL, so the trace attaches to the
latest CitizenRequest of the conversation that submitted the follow-up
(submitter_ref), falling back to the cluster's latest member request when
that conversation never filed a complaint of its own.
"""
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, Field

from app import db, stt
from app.gemini import GeminiUnavailable, call_gemini
from app.trace import create_run_trace, set_status, traced_stage

RESOLVED_STATES = ("resolved_unverified", "resolved_verified")


class PlausibilityJudgement(BaseModel):
    """Schema-bound Verify output — exactly one of the three spec outcomes."""

    result: Literal["match", "mismatch", "needs_human_review"]
    reason: str = Field(min_length=1, description="one-sentence justification")


_PHOTO_PROMPT = """You are the Verify stage of Setu, a civic infrastructure \
demand platform for Pune district, India. A cluster of citizen complaints \
was marked RESOLVED by officials — resolution is a claim, not a fact, until \
verified. The original complaint (the cluster's representative summary):

---
{summary}
---

The attached photo is a citizen's follow-up evidence about that issue.\
{pair_note}{transcript_block}

Judge plausibility: is the follow-up consistent with the reported issue \
having actually been fixed?

Respond with a JSON object only, matching exactly these keys:
- "result": "match" if the follow-up plausibly shows the issue resolved, \
"mismatch" if it contradicts the resolution claim (the problem is still \
visible or the evidence shows something else), or "needs_human_review" if \
you cannot judge from this evidence.
- "reason": one plain-English sentence justifying the result."""

_VOICE_PROMPT = """You are the Verify stage of Setu, a civic infrastructure \
demand platform for Pune district, India. A cluster of citizen complaints \
was marked RESOLVED by officials — resolution is a claim, not a fact, until \
verified. The original complaint (the cluster's representative summary):

---
{summary}
---

A citizen sent a follow-up voice note about that issue, transcribed locally:

---
{transcript}
---

Judge plausibility: is the follow-up consistent with the reported issue \
having actually been fixed?

Respond with a JSON object only, matching exactly these keys:
- "result": "match" if the follow-up plausibly confirms the issue is \
resolved, "mismatch" if it says the problem persists or contradicts the \
resolution claim, or "needs_human_review" if you cannot judge from it.
- "reason": one plain-English sentence justifying the result."""


def _judge(cluster_summary: str, media_paths: list[str],
           voice_path: str | None, _caller=None) -> tuple[PlausibilityJudgement, str | None]:
    """Run the plausibility check. Returns (judgement, transcript|None).

    Photo path when any photo exists (spec: both-media submissions use the
    vision path, transcript as added context). The LAST photo is sent — for a
    before/after pair that is the "after" evidence — with the pair noted in
    the prompt.
    """
    transcript: str | None = None
    if voice_path:
        transcript, _lang = stt.transcribe(voice_path)

    if media_paths:
        image_bytes = Path(media_paths[-1]).read_bytes()
        pair_note = ""
        if len(media_paths) > 1:
            pair_note = (f" It is the most recent of {len(media_paths)} "
                         "submitted photos (e.g. the \"after\" photo of a "
                         "before/after pair).")
        transcript_block = ""
        if transcript:
            transcript_block = ("\n\nThe citizen also sent a voice note, "
                                f"transcribed locally:\n---\n{transcript}\n---")
        judgement = call_gemini(
            stage="verify",
            prompt=_PHOTO_PROMPT.format(summary=cluster_summary,
                                        pair_note=pair_note,
                                        transcript_block=transcript_block),
            schema=PlausibilityJudgement,
            image_bytes=image_bytes,
            _caller=_caller,
        )
        return judgement, transcript

    judgement = call_gemini(
        stage="verify",
        prompt=_VOICE_PROMPT.format(summary=cluster_summary,
                                    transcript=transcript or ""),
        schema=PlausibilityJudgement,
        _caller=_caller,
    )
    return judgement, transcript


def _trace_request_id(conn: psycopg.Connection, submitter_ref: str,
                      cluster_id: str) -> str | None:
    """CitizenRequest the verify RunTrace attaches to (NOT NULL FK).

    The latest request of the submitting conversation; if that conversation
    never filed one, the cluster's latest member request (a cluster always
    has members).
    """
    row = conn.execute(
        """SELECT id::text FROM citizen_requests WHERE submitter_ref = %s
           ORDER BY submitted_at DESC LIMIT 1""",
        (submitter_ref,),
    ).fetchone()
    if row is not None:
        return row[0]
    row = conn.execute(
        """SELECT cr.id::text
           FROM cluster_memberships cm
           JOIN geocoded_requests gr ON gr.id = cm.geocoded_request_id
           JOIN structured_requests sr ON sr.id = gr.structured_request_id
           JOIN citizen_requests cr ON cr.id = sr.citizen_request_id
           WHERE cm.demand_cluster_id = %s
           ORDER BY cr.submitted_at DESC LIMIT 1""",
        (cluster_id,),
    ).fetchone()
    return row[0] if row else None


def run_verification(record_id: str, *, _caller=None) -> str:
    """Execute the Verify stage for one pending VerificationRecord.

    Called as a background task right after the follow-up is persisted (the
    same async-kick posture as intake). Returns the recorded result. This
    function never raises on a check failure — the failure IS an outcome
    (needs_human_review + flagged), and the submission is retained.
    """
    with db.pool.connection() as conn:
        rec = conn.execute(
            """SELECT vr.demand_cluster_id::text, vr.media_paths, vr.voice_path,
                      vr.submitter_ref, dc.representative_summary
               FROM verification_records vr
               JOIN demand_clusters dc ON dc.id = vr.demand_cluster_id
               WHERE vr.id = %s""",
            (record_id,),
        ).fetchone()
        if rec is None:
            raise ValueError(f"unknown verification_record {record_id}")
        cluster_id, media_paths, voice_path, submitter_ref, summary = rec

        cr_id = _trace_request_id(conn, submitter_ref, cluster_id)
        if cr_id is None:  # unreachable for a real cluster; belt-and-braces
            raise ValueError(f"no citizen_request to attach the Verify trace "
                             f"for record {record_id}")

        # The verify trace must not distort the request's observable pipeline
        # status (the citizen poll reads the LATEST trace): on completion it
        # takes over the request's current status, defaulting to 'published'
        # (the cluster was published before it could be resolved).
        prior = conn.execute(
            """SELECT status::text FROM run_traces WHERE citizen_request_id = %s
               ORDER BY created_at DESC LIMIT 1""",
            (cr_id,),
        ).fetchone()
        final_status = prior[0] if prior else "published"

        trace_id = create_run_trace(conn, cr_id)
        with traced_stage(conn, trace_id, "Verify", input_ref=record_id) as entry:
            transcript = None
            try:
                judgement, transcript = _judge(summary or "", media_paths or [],
                                               voice_path, _caller=_caller)
                result, reason = judgement.result, judgement.reason
            except GeminiUnavailable as exc:
                # call_gemini already retried once (spec retry posture);
                # a double failure defaults to human review — NEVER match,
                # never dropped, never auto-closed.
                result = "needs_human_review"
                reason = f"plausibility check unavailable after retry: {exc}"
                entry["retried"] = True
                entry["check_error"] = str(exc)
            except Exception as exc:
                # Local failure (STT, unreadable media): same defaulting —
                # a check failure is an outcome, not a dropped submission.
                result = "needs_human_review"
                reason = f"plausibility check failed: {exc}"
                entry["check_error"] = str(exc)

            flagged = result != "match"
            conn.execute(
                """UPDATE verification_records SET result = %s, flagged = %s
                   WHERE id = %s""",
                (result, flagged, record_id),
            )
            if result == "match":
                # Confirmed: cluster → resolved_verified. ConfidenceLevel is
                # deliberately untouched — it stays high (verification spec).
                conn.execute(
                    """UPDATE demand_clusters SET status = 'resolved_verified'
                       WHERE id = %s AND status = ANY(%s)""",
                    (cluster_id, list(RESOLVED_STATES)),
                )
            # mismatch / needs_human_review: the cluster is NOT touched — it
            # stays resolved_unverified until a human records a review
            # decision; no automated path clears the flag.
            conn.commit()

            entry["output_ref"] = record_id
            entry["result"] = result
            entry["reason"] = reason
            entry["flagged"] = flagged
            if transcript is not None:
                entry["transcript"] = transcript
        set_status(conn, trace_id, final_status)
    return result
