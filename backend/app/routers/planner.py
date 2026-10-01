"""Investment planner endpoints (enhancements design D4). Advisory; no writes."""
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import db, planner
from app.constants import EQUITY_CATEGORIES

router = APIRouter(prefix="/api/planner", tags=["planner"])

Category = str  # validated below against EQUITY_CATEGORIES


class WhatIf(BaseModel):
    category: str = Field(pattern="|".join(f"^{c}$" for c in EQUITY_CATEGORIES))
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Allocate(BaseModel):
    category: str = Field(pattern="|".join(f"^{c}$" for c in EQUITY_CATEGORIES))
    n: int = Field(ge=1, le=20)


@router.post("/whatif")
def whatif(body: WhatIf) -> dict[str, Any]:
    with db.pool.connection() as conn:
        out = planner.whatif(conn, body.category, body.lat, body.lon)
        conn.rollback()  # read-only by construction; never commit anything
    return out


@router.post("/allocate")
def allocate(body: Allocate) -> dict[str, Any]:
    with db.pool.connection() as conn:
        out = planner.allocate(conn, body.category, body.n)
        conn.rollback()
    return out
