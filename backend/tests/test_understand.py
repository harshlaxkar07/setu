"""Understand stage tests (tasks 3.7, parts of 3.4/3.6 contract).

All Gemini calls are mocked via call_gemini's `_caller` injection — never
live. STT is mocked at app.stt.transcribe — the real model download is
exercised separately (task 3.6 in-container check).
"""
import json
import os
import uuid
from pathlib import Path

import pytest

from app import gemini as gemini_mod
from app import stt
from app.gemini import GeminiUnavailable
from app.stages import locate as locate_mod
from app.stages import understand
from tests.conftest_a import (
    cleanup_test_rows,
    connect,
    make_citizen_request,
)

HINDI_LINE = "हमारे गाँव में कई हफ़्तों से पीने का पानी ठीक से नहीं आ रहा है।"

VALID_EXTRACTION = {
    "category": "water_infrastructure",
    "urgency": "high",
    "summary": "Drinking water has not been supplied properly for weeks",
    "detected_language": "Hindi",
    "raw_location_mention": "Velhe",
}


def caller_returning(payload) -> callable:
    """A `_caller` stand-in: returns fixed JSON, never touches the network."""
    text = payload if isinstance(payload, str) else json.dumps(payload)

    def _call(prompt, image_bytes=None):
        return text

    return _call


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    # Redirect fixture recording away from the bind-mounted fixture store.
    monkeypatch.setattr(gemini_mod, "FIXTURE_DIR", tmp_path)
    monkeypatch.setattr(locate_mod, "FIXTURE_DIR", tmp_path)
    c = connect()
    yield c
    cleanup_test_rows(c)
    c.close()


def test_text_request_understood_and_raw_row_untouched(conn):
    """Valid extraction → one StructuredRequest referencing the CitizenRequest;
    the raw row is byte-for-byte what ingestion persisted (spec scenario)."""
    cr = make_citizen_request(conn, text=HINDI_LINE)
    before = conn.execute(
        """SELECT channel, raw_text, audio_path, submitter_ref, submitted_at
           FROM citizen_requests WHERE id = %s""", (cr,)).fetchone()

    sr_id = understand.run(conn, cr, _caller=caller_returning(VALID_EXTRACTION))

    row = conn.execute(
        """SELECT citizen_request_id::text, category, urgency, summary,
                  detected_language, raw_location_mention
           FROM structured_requests WHERE id = %s""", (sr_id,)).fetchone()
    assert row == (cr, "water_infrastructure", "high",
                   VALID_EXTRACTION["summary"], "Hindi", "Velhe")

    after = conn.execute(
        """SELECT channel, raw_text, audio_path, submitter_ref, submitted_at
           FROM citizen_requests WHERE id = %s""", (cr,)).fetchone()
    assert after == before  # immutable raw request


def test_voice_transcription_persisted_before_failed_understand(conn, monkeypatch):
    """STT runs first and its row is committed even when Understand fails —
    and no StructuredRequest with fabricated defaults is produced."""
    calls = []

    def fake_transcribe(path):
        calls.append(path)
        return HINDI_LINE, "Hindi"

    monkeypatch.setattr(stt, "transcribe", fake_transcribe)
    cr = make_citizen_request(conn, channel="voice", text=None,
                              audio_path="/media/test-note.webm")

    with pytest.raises(Exception):  # malformed output fails the stage contract
        understand.run(conn, cr, _caller=caller_returning("this is not json"))

    assert calls == ["/media/test-note.webm"]
    t = conn.execute(
        "SELECT text, model FROM transcriptions WHERE citizen_request_id = %s",
        (cr,)).fetchone()
    assert t is not None and t[0] == HINDI_LINE
    assert t[1] == stt.model_name()
    assert conn.execute(
        "SELECT 1 FROM structured_requests WHERE citizen_request_id = %s",
        (cr,)).fetchone() is None
    # raw request remains available for reprocessing
    assert conn.execute(
        "SELECT 1 FROM citizen_requests WHERE id = %s", (cr,)).fetchone()


def test_retry_reuses_persisted_transcription(conn, monkeypatch):
    """A retry after a failed Understand never redoes STT (design D3)."""
    monkeypatch.setattr(stt, "transcribe",
                        lambda path: (HINDI_LINE, "Hindi"))
    cr = make_citizen_request(conn, channel="voice", text=None,
                              audio_path="/media/test-note2.webm")
    with pytest.raises(Exception):
        understand.run(conn, cr, _caller=caller_returning("garbage"))

    def must_not_run(path):  # pragma: no cover - failure signal only
        raise AssertionError("STT re-ran on retry")

    monkeypatch.setattr(stt, "transcribe", must_not_run)
    sr_id = understand.run(conn, cr, _caller=caller_returning(VALID_EXTRACTION))
    assert conn.execute(
        "SELECT citizen_request_id::text FROM structured_requests WHERE id = %s",
        (sr_id,)).fetchone()[0] == cr


def test_malformed_missing_field_raises_without_row(conn):
    """Schema-bound extraction: a response missing a required field raises;
    nothing is fabricated."""
    bad = {k: v for k, v in VALID_EXTRACTION.items() if k != "urgency"}
    cr = make_citizen_request(conn, text="paani nahi hai test")
    with pytest.raises(Exception):
        understand.run(conn, cr, _caller=caller_returning(bad))
    assert conn.execute(
        "SELECT 1 FROM structured_requests WHERE citizen_request_id = %s",
        (cr,)).fetchone() is None


def test_hinglish_detected_language_stored(conn):
    ext = dict(VALID_EXTRACTION, detected_language="Hinglish",
               raw_location_mention="hamare gaon")
    cr = make_citizen_request(
        conn, text="paani nahi aa raha hai hamare gaon mein kai hafton se")
    sr_id = understand.run(conn, cr, _caller=caller_returning(ext))
    lang, cat = conn.execute(
        "SELECT detected_language, category FROM structured_requests WHERE id = %s",
        (sr_id,)).fetchone()
    assert lang == "Hinglish" and cat == "water_infrastructure"


def test_absent_location_mention_still_produces_row(conn):
    """No place named → StructuredRequest still produced, mention empty."""
    ext = dict(VALID_EXTRACTION, raw_location_mention="")
    cr = make_citizen_request(conn, text=f"paani kharab hai {uuid.uuid4()}")
    sr_id = understand.run(conn, cr, _caller=caller_returning(ext))
    assert conn.execute(
        "SELECT raw_location_mention FROM structured_requests WHERE id = %s",
        (sr_id,)).fetchone()[0] == ""


@pytest.mark.skipif(
    not (os.environ.get("WHISPER_MODEL_DIR")
         and any(Path(os.environ["WHISPER_MODEL_DIR"]).glob("models--*"))),
    reason="Whisper model not downloaded onto the volume yet (task 3.6 setup)")
def test_local_stt_runs_without_network(conn):
    """Task 3.6 integration: the real Faster-Whisper model loads from the
    mounted volume and transcribes fully locally (HF hub forced offline —
    a network dependency would fail the load)."""
    import subprocess

    os.environ["HF_HUB_OFFLINE"] = "1"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "quiet", "-f", "lavfi", "-i",
         "anullsrc=r=16000:cl=mono", "-t", "1", "/tmp/test-silence.wav"],
        check=True)
    text, language = stt.transcribe("/tmp/test-silence.wav")
    assert isinstance(text, str) and isinstance(language, str)


def test_api_failure_retries_once_then_raises_unavailable(conn):
    """Transient API errors: exactly one retry, then GeminiUnavailable —
    the raw request is untouched and reprocessable."""
    attempts = []

    def failing(prompt, image_bytes=None):
        attempts.append(1)
        raise RuntimeError("rate limited")

    cr = make_citizen_request(conn, text="bijli nahi hai test")
    with pytest.raises(GeminiUnavailable):
        understand.run(conn, cr, _caller=failing)
    assert len(attempts) == 2  # retry-once posture
    assert conn.execute(
        "SELECT 1 FROM citizen_requests WHERE id = %s", (cr,)).fetchone()
