"""LLM provider layer (enhancements design D16).

Every language-model and embedding call in Setu goes through the provider
selected by environment configuration — the pipeline never names a vendor:

    LLM_PROVIDER   gemini (default) | openai_compat
    LLM_BASE_URL   OpenAI-compatible endpoint, e.g. http://host.docker.internal:11434/v1
    LLM_MODEL      chat model name for openai_compat
    EMBED_MODEL    embedding model name for openai_compat
    LLM_API_KEY    bearer token for openai_compat (optional for local servers)

`call_gemini` (app.gemini) keeps its name as the pipeline-wide entry point for
backward compatibility; it resolves the provider here on every call.

Per-call metadata (provider, model, latency, tokens) is collected in a context
variable and attached to the enclosing RunTrace stage by trace.traced_stage.
"""
import contextvars
import os

from app.llm.base import EmbeddingDimensionMismatch, Provider

_provider: Provider | None = None
_provider_key: tuple | None = None

# Calls made inside the current traced stage (None = not collecting).
_calls: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "setu_llm_calls", default=None)


def _config_key() -> tuple:
    return tuple(os.environ.get(k, "") for k in
                 ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "EMBED_MODEL"))


def get_provider() -> Provider:
    """The configured provider (rebuilt if the environment changed)."""
    global _provider, _provider_key
    key = _config_key()
    if _provider is None or key != _provider_key:
        name = (os.environ.get("LLM_PROVIDER") or "gemini").strip().lower()
        if name == "gemini":
            from app.llm.gemini_provider import GeminiProvider
            _provider = GeminiProvider()
        elif name in ("openai_compat", "openai-compat", "openai"):
            from app.llm.openai_compat import OpenAICompatProvider
            _provider = OpenAICompatProvider.from_env()
        else:
            raise ValueError(f"unknown LLM_PROVIDER {name!r} "
                             "(expected 'gemini' or 'openai_compat')")
        _provider_key = key
    return _provider


def embed(text: str) -> list[float]:
    """One embedding through the configured provider, PII-masked first."""
    return embed_many([text])[0] if text else []


def embed_many(texts: list[str]) -> list[list[float]]:
    from app import pii
    from app.constants import EMBEDDING_DIM
    masked = [pii.mask(t)[0] for t in texts]
    vecs = get_provider().embed(masked)
    for v in vecs:
        if len(v) != EMBEDDING_DIM:
            raise EmbeddingDimensionMismatch(
                f"{get_provider().name}/{get_provider().embed_model} returned "
                f"{len(v)}-dimension vectors; the vector column is {EMBEDDING_DIM}")
    return vecs


# --- trace metadata -----------------------------------------------------------

def begin_collecting() -> contextvars.Token:
    return _calls.set([])


def end_collecting(token: contextvars.Token) -> list[dict]:
    calls = _calls.get() or []
    _calls.reset(token)
    return calls


def record_call(meta: dict) -> None:
    calls = _calls.get()
    if calls is not None:
        calls.append(meta)


def check_embedding_dimension() -> str | None:
    """Startup probe for non-default providers. Returns an error message when
    the provider's vectors do not fit the schema column (None when fine)."""
    provider = get_provider()
    if provider.name == "gemini":
        return None  # dimensionality is requested explicitly (768)
    try:
        embed_many(["dimension probe"])
    except EmbeddingDimensionMismatch as exc:
        return str(exc)
    except Exception as exc:  # endpoint down: not a dimension verdict
        return f"embedding endpoint unreachable at startup: {exc}"
    return None
