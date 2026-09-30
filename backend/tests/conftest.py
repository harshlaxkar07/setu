"""Suite-wide test isolation.

Every test writes fixture-store entries (model replies, geocodes, embedding
cache) to a throwaway directory. The real store — backend/fixtures, committed
for DEMO_REPLAY — must only ever hold genuine recordings, never mock replies
produced by the test suite. Tests that need their own directory still
monkeypatch FIXTURE_DIR themselves (that override wins within the test).
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_fixture_store(tmp_path_factory, monkeypatch):
    from app import gemini
    from app.stages import locate

    store = tmp_path_factory.mktemp("fixture_store")
    monkeypatch.setattr(gemini, "FIXTURE_DIR", store)
    monkeypatch.setattr(locate, "FIXTURE_DIR", store)
