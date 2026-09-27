"""Local speech-to-text: Faster-Whisper `small`, loaded lazily, audio never
leaves the host (design D9, ADR-003).

Model files live under WHISPER_MODEL_DIR (a mounted volume in the container),
so the one-time download persists across container recreation. The model is
loaded exactly once per process and reused for every transcription.

Upgrade path is `medium` ONLY if the 8/10 Hindi bar fails on the real demo
recordings (task 3.9) — change constants.WHISPER_MODEL, nothing else.
"""
import hashlib
import json
import os
import threading
from pathlib import Path

from app.constants import WHISPER_MODEL

# Language-code → display-name mapping for the per-message language chip.
# Whisper reports ISO codes; the citizen surface shows friendly names.
_LANGUAGE_NAMES = {
    "hi": "Hindi",
    "en": "English",
    "mr": "Marathi",
    "ur": "Urdu",
}

_model = None
_model_lock = threading.Lock()


def model_name() -> str:
    """The value stored in transcriptions.model for provenance."""
    return f"faster-whisper-{WHISPER_MODEL}"


def get_model():
    """Lazily load the Faster-Whisper model once per process.

    download_root is the mounted volume (WHISPER_MODEL_DIR), so the first call
    ever downloads the model and every later call — including after container
    recreation — reuses the on-volume files.
    """
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # double-checked: one load even under threads
                from faster_whisper import WhisperModel

                _model = WhisperModel(
                    WHISPER_MODEL,
                    device="cpu",
                    compute_type="int8",  # CPU-friendly; hackathon hardware
                    download_root=os.environ["WHISPER_MODEL_DIR"],
                )
    return _model


def transcribe(audio_path: str) -> tuple[str, str]:
    """Transcribe one audio file locally. Returns (text, detected_language).

    No network call carries the audio anywhere (citizen-intake spec "Local
    speech-to-text transcription"): faster-whisper runs fully in-process.

    Replay posture (design D5, risk register): every successful transcription
    is recorded to a fixture keyed by the audio bytes' hash; with
    DEMO_REPLAY=1 a matching fixture answers first. Rehearsing the demo voice
    line once records its pre-transcribed fallback, so a live Whisper stumble
    on the rehearsed audio cannot sink the presentation.
    """
    fixture = _stt_fixture_path(audio_path)
    if os.environ.get("DEMO_REPLAY", "0") == "1" and fixture and fixture.exists():
        data = json.loads(fixture.read_text())
        return data["text"], data["language"]

    segments, info = get_model().transcribe(audio_path, beam_size=5)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    language = _LANGUAGE_NAMES.get(info.language, info.language or "unknown")

    if fixture:
        try:
            fixture.parent.mkdir(parents=True, exist_ok=True)
            fixture.write_text(json.dumps(
                {"text": text, "language": language}, ensure_ascii=False))
        except OSError:
            pass  # fixture recording is best-effort, never fails a transcription
    return text, language


def _stt_fixture_path(audio_path: str):
    """Fixture path for this audio's exact bytes; None if unreadable."""
    try:
        digest = hashlib.sha256(Path(audio_path).read_bytes()).hexdigest()
    except OSError:
        return None
    base = Path(os.environ.get("FIXTURE_DIR", "/app/fixtures"))
    return base / "stt" / f"{digest}.json"
