"""Publish Gate resume endpoint (§7, design D2).

``POST /api/gate/{thread_id}/resume`` is the ONLY mechanism that resolves a
suspended Publish Gate — the dashboard's Approve/Reject/Request-changes call
it; gate enforcement never depends on UI behavior. An unknown or
non-suspended thread returns 409 with no Approval recorded and no state
changed (orchestration spec).
"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import pipeline

router = APIRouter(prefix="/api/gate", tags=["gate"])


class GateDecision(BaseModel):
    decision: Literal["approved", "rejected", "needs_revision"]
    reviewer: str = Field(min_length=1, max_length=200)


@router.post("/{thread_id}/resume")
def resume(thread_id: str, body: GateDecision) -> dict:
    try:
        outcome = pipeline.resume_gate(thread_id, body.decision, body.reviewer)
    except pipeline.NotSuspended:
        raise HTTPException(
            status_code=409,
            detail="thread is unknown or not suspended at a Publish Gate; "
                   "no approval recorded, no state changed",
        )
    return {"thread_id": thread_id, "decision": body.decision, **outcome}
