"""Equity insight endpoints (enhancements design D3). Read-only, advisory."""
from typing import Any

from fastapi import APIRouter, HTTPException

from app import db, insights
from app.constants import EQUITY_CATEGORIES

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/silent-regions")
def silent_regions(category: str | None = None) -> list[dict[str, Any]]:
    cats = EQUITY_CATEGORIES
    if category:
        if category not in EQUITY_CATEGORIES:
            raise HTTPException(status_code=422,
                                detail=f"category must be one of {EQUITY_CATEGORIES}")
        cats = (category,)
    with db.pool.connection() as conn:
        return insights.silent_regions(conn, cats)


@router.get("/ranking")
def ranking(category: str) -> list[dict[str, Any]]:
    with db.pool.connection() as conn:
        return insights.ranking_comparison(conn, category)


@router.get("/trends")
def trends(category: str | None = None, days: int = 60) -> list[dict[str, Any]]:
    days = max(1, min(days, 365))
    with db.pool.connection() as conn:
        return insights.trends(conn, category, days)
