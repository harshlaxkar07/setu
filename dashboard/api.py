"""HTTP client for the Setu backend — the dashboard's ONLY data source.

Every view renders from these calls over BACKEND_URL (design D6): the dashboard
container has no database credentials, so the Publish Gate can never be
bypassed by a direct query. Nothing here mutates local state optimistically —
callers act only on a confirmed backend response.

The §8 verification-review endpoints do not exist yet: their helpers tolerate a
404 gracefully (empty list / explicit "not available" error) so the dashboard
side of that surface is already wired when §8 lands. Expected §8 contract,
mirroring the gate pattern:
    GET  /api/verifications?flagged=true
    POST /api/verifications/{record_id}/review   {"decision", "reviewer"}
"""
import os
from typing import Any

import httpx

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
TIMEOUT = 8.0


class ApiError(Exception):
    """A failed backend call, carrying a human-readable reason."""


def _get(path: str, params: dict | None = None) -> Any:
    try:
        resp = httpx.get(f"{BACKEND_URL}{path}", params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        raise ApiError(
            f"backend returned {exc.response.status_code} for {path}"
        ) from exc
    except httpx.HTTPError as exc:
        raise ApiError(f"backend unreachable at {BACKEND_URL}: {exc}") from exc


def _post(path: str, body: dict | None = None) -> tuple[Any, str | None]:
    """POST returning (payload, error). error is None only on a confirmed 2xx —
    the caller must not change any displayed state unless error is None."""
    try:
        resp = httpx.post(f"{BACKEND_URL}{path}", json=body, timeout=TIMEOUT)
        if resp.is_success:
            return resp.json(), None
        detail = ""
        try:
            detail = resp.json().get("detail", "")
        except Exception:
            detail = resp.text[:200]
        return None, f"backend refused ({resp.status_code}): {detail}"
    except httpx.HTTPError as exc:
        return None, f"backend unreachable: {exc}"


# --- read API (backend/app/routers/clusters.py) -------------------------------

def get_clusters() -> list[dict]:
    """All clusters with centroid, composition, score+tier+components."""
    return _get("/api/clusters")


def get_cluster(cluster_id: str) -> dict:
    """One cluster in full: indicators, gap, breakdown, sample raw requests."""
    return _get(f"/api/clusters/{cluster_id}")


def get_cluster_trace(cluster_id: str) -> list[dict]:
    """Run traces for the cluster's member requests (empty pre-§7)."""
    return _get(f"/api/clusters/{cluster_id}/trace")


def get_recommendations(status: str) -> list[dict]:
    """status: 'published' (derives solely from approvals), 'pending', or
    'needs_revision' (sent back via Request-changes)."""
    return _get("/api/recommendations", params={"status": status})


# --- actions (always backend-confirmed, never optimistic) ----------------------

def post_gate_decision(
    thread_id: str, decision: str, reviewer: str
) -> tuple[Any, str | None]:
    """Approve / Reject / Request-changes → §7's gate resume endpoint.

    decision ∈ {'approved', 'rejected', 'needs_revision'}.
    """
    return _post(
        f"/api/gate/{thread_id}/resume",
        {"decision": decision, "reviewer": reviewer},
    )


def post_mark_resolved(cluster_id: str) -> tuple[Any, str | None]:
    """Simulated mark-resolved: published → resolved_unverified."""
    return _post(f"/api/clusters/{cluster_id}/resolve")


# --- §8 verification review (404-tolerant until the bolt-on lands) -------------

def get_flagged_verifications() -> tuple[list[dict], bool]:
    """(records, available). available=False while §8's endpoint is absent."""
    try:
        resp = httpx.get(
            f"{BACKEND_URL}/api/verifications",
            params={"flagged": "true"}, timeout=TIMEOUT,
        )
        if resp.status_code == 404:
            return [], False
        resp.raise_for_status()
        return resp.json(), True
    except httpx.HTTPError:
        return [], False


def post_verification_review(
    record_id: str, decision: str, reviewer: str
) -> tuple[Any, str | None]:
    """decision ∈ {'confirm_resolved', 'reject_resolution'} (§8 endpoint)."""
    return _post(
        f"/api/verifications/{record_id}/review",
        {"decision": decision, "reviewer": reviewer},
    )
