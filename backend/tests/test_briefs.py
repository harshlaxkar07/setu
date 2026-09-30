"""Bilingual policy brief (enhancements task 7.1, design D12)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest_a import connect, ensure_pool


@pytest.fixture(scope="module")
def client():
    ensure_pool()
    return TestClient(app)


def _cluster(where: str) -> str:
    with connect() as conn:
        return conn.execute(
            f"""SELECT dc.id::text FROM demand_clusters dc
                JOIN region_profiles rp ON ST_Contains(rp.boundary, dc.centroid)
                WHERE {where}""").fetchone()[0]


def test_approved_brief_has_every_indicator_breakdown_and_approval(client):
    cid = _cluster("dc.category = 'sanitation'")
    html = client.get(f"/api/briefs/{cid}").text
    with connect() as conn:
        indicators = conn.execute(
            "SELECT name, value_text FROM priority_indicators WHERE demand_cluster_id = %s",
            (cid,)).fetchall()
        score = conn.execute("SELECT score FROM priority_scores WHERE demand_cluster_id=%s",
                             (cid,)).fetchone()[0]
        reviewer, decided = conn.execute(
            """SELECT a.reviewer, a.decided_at FROM approvals a JOIN recommendations r
                 ON r.id = a.recommendation_id WHERE r.demand_cluster_id = %s""",
            (cid,)).fetchone()
    assert indicators
    for name, text in indicators:
        assert name in html and text in html
    assert f"{float(score):.3f}" in html                    # score breakdown total
    assert "Infrastructure gap" in html and "बुनियादी ढाँचे की कमी" in html
    assert f"Approved by {reviewer} on {decided:%d %b %Y}" in html  # English
    assert "द्वारा" in html and "स्वीकृत" in html               # Hindi
    assert "✦ AI-drafted" in html
    assert "DRAFT — AWAITING REVIEW" not in html


def test_unapproved_brief_is_watermarked_in_both_languages(client):
    cid = _cluster("rp.name = 'Velhe' AND dc.category = 'water_infrastructure'")
    html = client.get(f"/api/briefs/{cid}").text
    assert "DRAFT — AWAITING REVIEW" in html and "ड्राफ़्ट — समीक्षा बाक़ी" in html
    assert "No recommendation drafted yet." in html


def test_brief_contains_no_unstored_text(client):
    """Only stored rows reach the brief: no model call is made to render it."""
    from app import gemini
    calls = []
    orig = gemini._live_call
    gemini._live_call = lambda *a, **k: calls.append(a) or ""
    try:
        cid = _cluster("dc.category = 'sanitation'")
        assert client.get(f"/api/briefs/{cid}").status_code == 200
    finally:
        gemini._live_call = orig
    assert calls == []


def test_download_sets_attachment_filename(client):
    cid = _cluster("dc.category = 'sanitation'")
    r = client.get(f"/api/briefs/{cid}", params={"download": "true"})
    assert r.headers["content-disposition"].startswith('attachment; filename="setu-brief-')


def test_unknown_cluster_is_404(client):
    assert client.get("/api/briefs/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/briefs/not-a-uuid").status_code == 404
