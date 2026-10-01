"""Task 9.1: the DEMO_REPLAY cached-replay layer around the Gemini client.

- DEMO_REPLAY=1 + fixture hit → ZERO live calls, identical validated result.
- DEMO_REPLAY=1 + fixture miss → clean fall-through to the live path.
- Pipeline logic is identical in both modes: the wrapper is the only switch.
"""
import json

import pytest
from pydantic import BaseModel

from app import gemini


class Toy(BaseModel):
    answer: str


@pytest.fixture()
def fixture_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini, "FIXTURE_DIR", tmp_path)
    return tmp_path


def test_fixture_hit_makes_zero_live_calls(fixture_dir, monkeypatch):
    calls = {"n": 0}

    def live(prompt, image_bytes=None):
        calls["n"] += 1
        return json.dumps({"answer": "live"})

    # Record once in live mode (DEMO_REPLAY off).
    monkeypatch.setenv("DEMO_REPLAY", "0")
    out = gemini.call_gemini("demo", "rehearsed prompt", schema=Toy, _caller=live)
    assert out.answer == "live" and calls["n"] == 1

    # Replay: the recorded fixture answers; the live path is never touched.
    monkeypatch.setenv("DEMO_REPLAY", "1")
    out2 = gemini.call_gemini("demo", "rehearsed prompt", schema=Toy, _caller=live)
    assert out2.answer == "live"
    assert calls["n"] == 1  # zero additional live calls on the fixture hit


def test_fixture_miss_falls_through_to_live(fixture_dir, monkeypatch):
    calls = {"n": 0}

    def live(prompt, image_bytes=None):
        calls["n"] += 1
        return json.dumps({"answer": "fresh"})

    monkeypatch.setenv("DEMO_REPLAY", "1")
    out = gemini.call_gemini("demo", "unrehearsed judge question",
                             schema=Toy, _caller=live)
    assert out.answer == "fresh"
    assert calls["n"] == 1  # clean fall-through on the miss


def test_replay_keys_are_stage_and_input_scoped(fixture_dir, monkeypatch):
    monkeypatch.setenv("DEMO_REPLAY", "1")
    gemini.call_gemini("stage_a", "same prompt",
                       _caller=lambda p, image_bytes=None: "A")
    # Same prompt, different stage: its own fixture, not stage_a's.
    got = gemini.call_gemini("stage_b", "same prompt",
                             _caller=lambda p, image_bytes=None: "B")
    assert got == "B"
    # And the recorded fixtures now replay independently with no live caller.
    boom = lambda p, image_bytes=None: (_ for _ in ()).throw(RuntimeError("live!"))
    assert gemini.call_gemini("stage_a", "same prompt", _caller=boom) == "A"
    assert gemini.call_gemini("stage_b", "same prompt", _caller=boom) == "B"


def test_raw_newline_inside_json_string_is_accepted(fixture_dir):
    """Gemini occasionally breaks a string value across lines; the payload is
    still the intended JSON and must validate (observed live, 2026-09-30)."""
    raw = '{\n  "name": "line one\nline two"\n}'

    class Named(BaseModel):
        name: str

    out = gemini.call_gemini("demo", "p", schema=Named, _caller=lambda p, i: raw)
    assert out.name == "line one\nline two"


def test_strict_replay_missing_recording_never_calls_provider(fixture_dir):
    from app import replay

    def forbidden(*args):
        pytest.fail("Offline replay called the provider")

    with replay.mode(replay=True, strict=True):
        with pytest.raises(replay.MissingRecording):
            gemini.call_gemini("understand", "missing", _caller=forbidden)


def test_invalid_model_output_is_not_recorded(fixture_dir):
    with pytest.raises(gemini._ValidationFailed):
        gemini.call_gemini("demo", "invalid", schema=Toy, _caller=lambda p, i: "bad")
    assert not list(fixture_dir.glob("*.json"))


def test_scoped_live_mode_overrides_environment_and_restores_it(monkeypatch):
    from app import replay
    monkeypatch.setenv("DEMO_REPLAY", "1")
    with replay.mode(replay=False):
        assert not gemini._replay_enabled()
    assert gemini._replay_enabled()
