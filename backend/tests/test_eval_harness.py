"""Evaluation harness mechanics (enhancements task 9.2): scoring, the
per-language summary, cleanup and determinism — with every external call
mocked, so this proves the harness, not the model's accuracy."""
import json

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
    report = run_eval.run(replay=True, report_path=tmp_path / "r.json", **_mocks())
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
    a = run_eval.run(replay=True, limit=12, report_path=tmp_path / "a.json", **_mocks())
    b = run_eval.run(replay=True, limit=12, report_path=tmp_path / "b.json", **_mocks())
    assert a["summary"] == b["summary"]
