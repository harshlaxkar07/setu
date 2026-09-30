"""Evaluation harness mechanics (enhancements task 9.2): scoring, the
per-language summary, cleanup and determinism — with every external call
mocked, so this proves the harness, not the model's accuracy."""
import json
import pytest

from eval import dataset, run_eval
from tests.conftest_a import connect


def _mocks():
    """Perfect Understand answers from the labels; geocoder finds nothing (so
    the region fallback resolves named places); constant embedding."""
    by_text = {i["text"]: i for i in dataset.load()}

    def caller(prompt, image_bytes=None):
        item = next(i for t, i in by_text.items() if t in prompt)
        return json.dumps({"category": item["category"], "urgency": item["urgency"],
                           "summary": "s", "detected_language": item["language"],
                           "raw_location_mention": item["location"] or ""})
    return {"understand_caller": caller, "transport": lambda q: [],
            "embedder": lambda t: [0.03] * 768}


def test_report_scores_and_cleans_up(tmp_path):
    report = run_eval.run(replay=False, report_path=tmp_path / "r.json", **_mocks())
    s = report["summary"]
    assert s["items"] == len(dataset.load()) and s["errors"] == 0
    assert s["overall"]["category"] == 1.0 and s["overall"]["urgency"] == 1.0
    assert set(s["by_language"]) == set(dataset.LANGUAGES)
    # Every labelled place resolves via the region fallback; unlocatable stay so.
    assert s["overall"]["location"] == 1.0
    assert json.loads((tmp_path / "r.json").read_text())["summary"] == s
    with connect() as conn:
        (left,) = conn.execute(
            "SELECT count(*) FROM citizen_requests WHERE submitter_ref LIKE 'eval-%'").fetchone()
    assert left == 0


def test_two_runs_give_identical_figures(tmp_path):
    recorded = run_eval.run(replay=False, limit=12, report_path=tmp_path / "live.json", **_mocks())
    a = run_eval.run(replay=True, limit=12, report_path=tmp_path / "a.json")
    b = run_eval.run(replay=True, limit=12, report_path=tmp_path / "b.json")
    assert a["complete"] and b["complete"]
    assert recorded["summary"] == a["summary"] == b["summary"]


def test_missing_recordings_report_errors_without_network(tmp_path, monkeypatch):
    from app import gemini
    monkeypatch.setattr(gemini, "_live_call", lambda *a: pytest.fail("live call"))
    report = run_eval.run(replay=True, limit=2, report_path=tmp_path / "missing.json")
    assert not report["complete"]
    assert report["summary"]["errors"] == 2
    assert all(r["error_type"] == "MissingRecording" for r in report["results"])


def test_locate_failure_is_reported_and_rows_are_cleaned(tmp_path):
    mocks = _mocks()
    def failed_embedding(text):
        raise RuntimeError("embedding endpoint unavailable")
    mocks["embedder"] = failed_embedding
    report = run_eval.run(replay=False, limit=1, report_path=tmp_path / "failed.json", **mocks)
    assert not report["complete"] and report["summary"]["errors"] == 1
    assert "embedding endpoint unavailable" in report["results"][0]["error"]
    with connect() as conn:
        assert conn.execute("SELECT count(*) FROM citizen_requests WHERE submitter_ref LIKE 'eval-%'").fetchone()[0] == 0


def test_service_outage_stops_early_and_marks_report_incomplete(tmp_path):
    def unavailable(*args):
        raise RuntimeError("quota exhausted")
    report = run_eval.run(replay=False, limit=3, report_path=tmp_path / "outage.json",
                          understand_caller=unavailable)
    assert not report["complete"] and report["requested_items"] == 3
    assert report["summary"]["items"] == 1


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_limit_rejected(limit, tmp_path):
    with pytest.raises(ValueError, match="positive"):
        run_eval.run(replay=True, limit=limit, report_path=tmp_path / "unused.json")
