"""Understand stage: CitizenRequest → StructuredRequest (files/05 stage 1).

Voice requests are transcribed FIRST (locally, app.stt) and the transcription
row is committed BEFORE the LLM extraction runs — a failed Understand still
leaves the transcription persisted, and a retry never redoes STT (design D3).

Extraction is schema-bound through app.gemini.call_gemini: malformed model
output raises (`_ValidationFailed` inside call_gemini) instead of producing a
StructuredRequest with fabricated defaults (citizen-intake spec "Transcription
or understanding fails after ingestion").
"""
from typing import Literal

import psycopg
from pydantic import BaseModel, Field, field_validator

from app import stt
from app.constants import CATEGORIES, CATEGORY_OTHER
from app.gemini import call_gemini


class Extraction(BaseModel):
    """Schema-bound Understand output — the StructuredRequest fields.

    Every field is required (no defaults): a response missing any of them is
    malformed output and fails validation, never a silently-filled row.
    """

    category: str = Field(description="infrastructure category, snake_case")
    urgency: Literal["high", "medium", "low"]
    summary: str = Field(min_length=1, description="plain-language restatement")
    detected_language: str = Field(
        min_length=1, description="English name of the language, e.g. Marathi")
    raw_location_mention: str = Field(
        description="location exactly as spoken/typed; empty string if none"
    )

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        value = value.strip().lower().replace(" ", "_").replace("-", "_")
        return value if value in CATEGORIES else CATEGORY_OTHER


_PROMPT = """You are the Understand stage of Setu, a civic infrastructure \
demand platform in India. A citizen sent this message, in any language or a \
mix of languages:

---
{text}
---

Extract, as JSON matching exactly these keys:
- "category": exactly one of: {categories}. \
Use "healthcare" for hospitals, clinics, doctors, medicines or ambulances \
not reaching a health facility; use "road_infrastructure" when a damaged or \
missing road is the problem (even if ambulances are affected).
- "urgency": "high", "medium" or "low", judged from the described impact \
(health or safety risk, loss of drinking water, or blocked emergency access \
is high).
- "summary": one plain-English sentence restating the complaint.
- "detected_language": the English name of the message's language, for any \
language (e.g. "Hindi", "Marathi", "Tamil", "Bengali", "English"). Use \
"Hinglish" for Hindi written in Latin script, and "<Language>-English" for \
other mixes (e.g. "Marathi-English").
- "raw_location_mention": the place exactly as the citizen wrote or spoke it \
(village, ward, landmark phrase), verbatim and unresolved. Use "" if no \
place is mentioned.

Respond with the JSON object only."""


def _source_text(conn: psycopg.Connection, citizen_request_id: str,
                 channel: str, raw_text: str | None,
                 audio_path: str | None) -> str:
    """The text Understand reads: raw text, or the (persisted) transcription.

    For voice, an existing transcription row is reused — retries never redo
    STT — and a fresh one is committed before any LLM call so a failed
    Understand still leaves it behind (design D3).
    """
    if channel != "voice":
        if not raw_text:
            raise ValueError(f"citizen_request {citizen_request_id}: no raw_text")
        return raw_text

    row = conn.execute(
        """SELECT text FROM transcriptions
           WHERE citizen_request_id = %s ORDER BY created_at DESC LIMIT 1""",
        (citizen_request_id,),
    ).fetchone()
    if row is not None:
        return row[0]

    if not audio_path:
        raise ValueError(f"citizen_request {citizen_request_id}: voice without audio")
    text, language = stt.transcribe(audio_path)
    conn.execute(
        """INSERT INTO transcriptions (citizen_request_id, text, model,
                                       detected_language)
           VALUES (%s, %s, %s, %s)""",
        (citizen_request_id, text, stt.model_name(), language),
    )
    conn.commit()  # persisted BEFORE Understand runs (citizen-intake spec)
    return text


def run(conn: psycopg.Connection, citizen_request_id: str, *, _caller=None) -> str:
    """Derive exactly one StructuredRequest; returns structured_request_id.

    `_caller` is forwarded to call_gemini for test injection (never live
    Gemini in tests). Malformed LLM output raises — no fabricated defaults.
    """
    row = conn.execute(
        "SELECT channel, raw_text, audio_path FROM citizen_requests WHERE id = %s",
        (citizen_request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown citizen_request {citizen_request_id}")
    channel, raw_text, audio_path = row

    text = _source_text(conn, citizen_request_id, channel, raw_text, audio_path)

    extraction: Extraction = call_gemini(
        stage="understand",
        prompt=_PROMPT.format(
            text=text, categories=", ".join(f'"{c}"' for c in CATEGORIES)),
        schema=Extraction,
        _caller=_caller,
    )

    sr = conn.execute(
        """INSERT INTO structured_requests
             (citizen_request_id, category, urgency, summary,
              detected_language, raw_location_mention)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (citizen_request_id, extraction.category, extraction.urgency,
         extraction.summary, extraction.detected_language,
         extraction.raw_location_mention),
    ).fetchone()
    conn.commit()
    return str(sr[0])
