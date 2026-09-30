"""Shared LLM entry point: schema-bound calls, retry-once posture, DEMO_REPLAY.

Every LLM call in the pipeline goes through `call_gemini` (design D5). The name
is historical: the call is served by whichever provider `app.llm` is configured
for (enhancements design D16) — Gemini by default:

- **Schema-bound**: pass a Pydantic model as `schema` and the call returns a
  validated instance; malformed output raises (the stage contract fails rather
  than passing garbage downstream).
- **Retry-once**: one retry on failure, then `GeminiUnavailable` — the caller
  (pipeline runner) halts the run as `needs-retry`; nothing is dropped.
- **DEMO_REPLAY** (ADR-002, task 9.1): with DEMO_REPLAY=1 the fixture store is
  consulted first, falling through to live Gemini on a miss. In live mode every
  successful response is recorded, so rehearsing once builds the demo fixtures.
  Pipeline logic is identical in both modes — this wrapper is the only switch.
"""
import contextvars
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Type

from pydantic import BaseModel

from app.constants import GEMINI_MODEL

FIXTURE_DIR = Path(os.environ.get("FIXTURE_DIR", "/app/fixtures"))


class GeminiUnavailable(Exception):
    """Raised after the single retry also fails — run halts as needs-retry."""


# Provider-neutral alias; existing callers keep catching GeminiUnavailable.
LLMUnavailable = GeminiUnavailable

# Token usage of the most recent live Gemini call in this context (read by the
# Gemini provider so the RunTrace can show it).
_last_usage: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "setu_gemini_usage", default={})


def _fixture_key(stage: str, prompt: str) -> str:
    return hashlib.sha256(f"{stage}\x00{prompt}".encode()).hexdigest()


def _fixture_path(key: str) -> Path:
    return FIXTURE_DIR / f"{key}.json"


def _replay_enabled() -> bool:
    return os.environ.get("DEMO_REPLAY", "0") == "1"


def _lookup_fixture(stage: str, prompt: str) -> str | None:
    path = _fixture_path(_fixture_key(stage, prompt))
    if path.exists():
        return json.loads(path.read_text())["response"]
    return None


def _record_fixture(stage: str, prompt: str, response: str) -> None:
    try:
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        _fixture_path(_fixture_key(stage, prompt)).write_text(
            json.dumps({"stage": stage, "prompt": prompt, "response": response})
        )
    except OSError:
        pass  # fixture recording is best-effort; never fail a live call over it


def _live_call(prompt: str, image_bytes: bytes | None) -> str:
    from langchain_core.messages import HumanMessage
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(model=GEMINI_MODEL)
    if image_bytes is not None:
        import base64
        mime = "image/png" if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"},
        ]
        msg = llm.invoke([HumanMessage(content=content)])
    else:
        msg = llm.invoke(prompt)
    usage = getattr(msg, "usage_metadata", None) or {}
    _last_usage.set({"input_tokens": usage.get("input_tokens"),
                     "output_tokens": usage.get("output_tokens")})
    return _content_text(msg.content)


def _content_text(content) -> str:
    """Flatten a model response to its text.

    Reasoning-tier Gemini models return a list of content parts (text plus
    thought/signature parts); only the text parts carry the answer.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
        if texts:
            return "\n".join(texts)
    return json.dumps(content)


def call_gemini(
    stage: str,
    prompt: str,
    schema: Type[BaseModel] | None = None,
    image_bytes: bytes | None = None,
    _caller=None,
) -> Any:
    """One pipeline LLM call. Returns `schema`-validated instance or raw text.

    `_caller` swaps the live-call function in tests (mock injection point).
    Citizen text is PII-masked before it can reach any provider or fixture
    (enhancements design D13).
    """
    from app import llm, pii

    provider = llm.get_provider()
    prompt, pii_counts = pii.mask(prompt)

    def live(p: str, img: bytes | None):
        if _caller is not None:
            return _caller(p, img), None, None
        done = provider.complete(p, img, json_mode=schema is not None)
        return done.text, done.input_tokens, done.output_tokens

    # Fixture keys stay (stage, prompt) for Gemini so committed demo fixtures
    # keep replaying; other providers get their own namespace.
    fixture_stage = stage if provider.name == "gemini" else \
        f"{stage}@{provider.name}/{provider.model}"
    # Fixture store first when replaying. Image calls key on prompt + image hash.
    fixture_prompt = prompt
    if image_bytes is not None:
        fixture_prompt = f"{prompt}\x00img:{hashlib.sha256(image_bytes).hexdigest()}"
    meta = {"stage": stage, "provider": provider.name, "model": provider.model,
            "pii_masked": pii_counts, "masked_prompt": prompt}
    if _replay_enabled():
        hit = _lookup_fixture(fixture_stage, fixture_prompt)
        if hit is not None:
            llm.record_call({**meta, "replayed": True, "latency_ms": 0.0})
            return _validate(hit, schema)

    last_err: Exception | None = None
    for attempt in (1, 2):  # exactly one retry (orchestration spec)
        start = time.monotonic()
        try:
            raw, tokens_in, tokens_out = live(prompt, image_bytes)
            llm.record_call({
                **meta, "replayed": False, "attempt": attempt,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "input_tokens": tokens_in, "output_tokens": tokens_out,
            })
            _record_fixture(fixture_stage, fixture_prompt, raw)
            return _validate(raw, schema)
        except _ValidationFailed:
            raise  # malformed output is a contract failure, not a transient error
        except Exception as exc:  # API error / rate limit — retry once
            last_err = exc
    raise GeminiUnavailable(
        f"{stage}: {provider.name} failed twice: {last_err}") from last_err


class _ValidationFailed(Exception):
    pass


def _validate(raw: str, schema: Type[BaseModel] | None) -> Any:
    if schema is None:
        return raw
    # Accept plain JSON or a ```json fenced block.
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.startswith("json") else text
    try:
        return schema.model_validate_json(text.strip())
    except Exception as exc:
        raise _ValidationFailed(f"schema-bound output invalid: {exc}") from exc
