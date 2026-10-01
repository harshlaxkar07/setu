"""Reviewer accounts and signed session tokens (enhancements design D15).

Decision actions (Publish Gate, verification review, trust review, mark
resolved) require a signed-in reviewer; the recorded reviewer identity comes
from the token, never from free text. Read endpoints stay open.

Configuration (.env):
    REVIEWERS       "Name=<salt>.<hash>;Other Name=<salt>.<hash>" — generate an
                    entry with: python3 scripts/hash_passcode.py "Name"
    SESSION_SECRET  random string signing session tokens; if unset, a
                    per-process secret is used (sessions end on restart).

Standard library only: scrypt for passcodes, HMAC-SHA256 for tokens.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Header, HTTPException

TOKEN_TTL_S = 8 * 3600
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
_process_secret = secrets.token_hex(32)


def hash_passcode(passcode: str, salt: bytes | None = None) -> str:
    """'<salt hex>.<hash hex>' — the value stored in REVIEWERS."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(passcode.encode(), salt=salt, **_SCRYPT)
    return f"{salt.hex()}.{digest.hex()}"


def _verify_passcode(passcode: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(".", 1)
        expected = bytes.fromhex(digest_hex)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    actual = hashlib.scrypt(passcode.encode(), salt=salt, **_SCRYPT)
    return hmac.compare_digest(actual, expected)


def reviewers() -> dict[str, str]:
    """name → stored passcode hash, from REVIEWERS."""
    out = {}
    for entry in (os.environ.get("REVIEWERS") or "").split(";"):
        name, sep, stored = entry.strip().partition("=")
        if sep and name.strip() and stored.strip():
            out[name.strip()] = stored.strip()
    return out


def _secret() -> bytes:
    return (os.environ.get("SESSION_SECRET") or _process_secret).encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(name: str, now: float | None = None) -> tuple[str, int]:
    exp = int((now or time.time()) + TOKEN_TTL_S)
    payload = _b64(json.dumps({"sub": name, "exp": exp}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}", exp


def login(name: str, passcode: str) -> tuple[str, int]:
    """(token, expiry) for a valid reviewer; raises 401 otherwise. Unknown
    names and wrong passcodes get the same message (no account probing)."""
    stored = reviewers().get(name.strip())
    # Hash even for unknown names so timing does not reveal which exist.
    ok = _verify_passcode(passcode, stored or hash_passcode("x", b"\0" * 16))
    if not (stored and ok):
        raise HTTPException(status_code=401,
                            detail="wrong reviewer name or passcode")
    return issue_token(name.strip())


def verify_token(token: str, now: float | None = None) -> str:
    """The reviewer name in a valid, unexpired token; raises 401 otherwise."""
    try:
        payload, sig = token.split(".", 1)
        expected = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        claims = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="invalid reviewer session")
    if claims.get("exp", 0) < (now or time.time()):
        raise HTTPException(status_code=401, detail="reviewer session expired — sign in again")
    name = claims.get("sub", "")
    if name not in reviewers():
        raise HTTPException(status_code=401, detail="reviewer account no longer configured")
    return name


def require_reviewer(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: the signed-in reviewer's name, or 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401,
                            detail="sign in as a reviewer to record decisions")
    return verify_token(authorization[7:].strip())
