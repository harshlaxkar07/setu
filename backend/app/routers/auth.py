"""Reviewer sign-in (enhancements design D15)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    passcode: str = Field(min_length=1, max_length=200)


@router.post("/login")
def login(body: Login) -> dict:
    token, exp = auth.login(body.name, body.passcode)
    return {"token": token, "reviewer": body.name.strip(), "expires_at": exp}


@router.get("/me")
def me(reviewer: str = Depends(auth.require_reviewer)) -> dict:
    return {"reviewer": reviewer}


@router.get("/reviewers")
def configured() -> dict:
    """Whether sign-in is possible at all (names only, never hashes)."""
    return {"configured": sorted(auth.reviewers())}
