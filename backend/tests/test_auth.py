"""Reviewer accounts and session tokens (enhancements task 4.1, design D15)."""
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth
from app.main import app


@pytest.fixture()
def reviewers(monkeypatch):
    monkeypatch.setenv("REVIEWERS", ";".join([
        f"Priya Sharma={auth.hash_passcode('correct horse')}",
        f"Demo Reviewer={auth.hash_passcode('setu-demo')}",
    ]))
    monkeypatch.setenv("SESSION_SECRET", "test-secret")


@pytest.fixture()
def client():
    return TestClient(app)


def test_correct_login_issues_working_token(reviewers, client):
    r = client.post("/api/auth/login",
                    json={"name": "Priya Sharma", "passcode": "correct horse"})
    assert r.status_code == 200
    body = r.json()
    assert body["reviewer"] == "Priya Sharma" and body["expires_at"] > time.time()
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.json() == {"reviewer": "Priya Sharma"}


@pytest.mark.parametrize("name,passcode", [
    ("Priya Sharma", "wrong"),
    ("Nobody", "correct horse"),
])
def test_wrong_passcode_or_unknown_name_is_401_with_same_message(
        reviewers, client, name, passcode):
    r = client.post("/api/auth/login", json={"name": name, "passcode": passcode})
    assert r.status_code == 401
    assert r.json()["detail"] == "wrong reviewer name or passcode"
    assert "token" not in r.json()


def test_expired_token_is_rejected(reviewers):
    token, _ = auth.issue_token("Priya Sharma", now=time.time() - auth.TOKEN_TTL_S - 5)
    with pytest.raises(HTTPException) as exc:
        auth.verify_token(token)
    assert exc.value.status_code == 401 and "expired" in exc.value.detail


def test_forged_token_is_rejected(reviewers, monkeypatch):
    # Signed with a different secret …
    monkeypatch.setenv("SESSION_SECRET", "attacker-secret")
    forged, _ = auth.issue_token("Priya Sharma")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    with pytest.raises(HTTPException) as exc:
        auth.verify_token(forged)
    assert exc.value.status_code == 401
    # … or a valid token with its payload swapped for another name.
    good, _ = auth.issue_token("Priya Sharma")
    other, _ = auth.issue_token("Demo Reviewer")
    tampered = other.split(".")[0] + "." + good.split(".")[1]
    with pytest.raises(HTTPException):
        auth.verify_token(tampered)


def test_removed_account_token_stops_working(reviewers, monkeypatch):
    token, _ = auth.issue_token("Demo Reviewer")
    monkeypatch.setenv("REVIEWERS", f"Priya Sharma={auth.hash_passcode('x')}")
    with pytest.raises(HTTPException):
        auth.verify_token(token)


def test_missing_header_is_401(client):
    assert client.get("/api/auth/me").status_code == 401


def test_reviewer_listing_exposes_names_only(reviewers, client):
    body = client.get("/api/auth/reviewers").json()
    assert body == {"configured": ["Demo Reviewer", "Priya Sharma"]}
