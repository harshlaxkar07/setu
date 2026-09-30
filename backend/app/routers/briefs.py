"""Policy brief download (enhancements design D12). Read-only."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app import briefs, db

router = APIRouter(prefix="/api/briefs", tags=["briefs"])


@router.get("/{cluster_id}", response_class=HTMLResponse)
def brief(cluster_id: str, download: bool = False) -> HTMLResponse:
    with db.pool.connection() as conn:
        try:
            data = briefs.load(conn, cluster_id)
        except Exception:
            data = None
    if data is None:
        raise HTTPException(status_code=404, detail="cluster not found")
    headers = {}
    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="setu-brief-{cluster_id[:8]}.html"')
    return HTMLResponse(briefs.render(data), headers=headers)
