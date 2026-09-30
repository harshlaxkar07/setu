"""Provider abstraction (enhancements task 1.4, design D16) — mocked HTTP."""
import json

import httpx
import pytest

from app import gemini, llm
from app.llm.base import EmbeddingDimensionMismatch
from app.llm.openai_compat import OpenAICompatProvider


def _provider(handler, **kw):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatProvider("http://local:11434/v1", "llama3.1", "nomic-embed",
                                client=client, **kw)


def test_chat_completion_json_mode_and_usage():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5}})

    done = _provider(handler).complete("hi", None, json_mode=True)
    assert seen["url"] == "http://local:11434/v1/chat/completions"
    assert seen["body"]["model"] == "llama3.1"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert (done.text, done.input_tokens, done.output_tokens) == ('{"ok": true}', 12, 5)


def test_api_key_sent_as_bearer():
    def handler(req):
        assert req.headers["authorization"] == "Bearer s3cret"
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})
    _provider(handler, api_key="s3cret").complete("hi", None)


def test_embeddings_in_index_order():
    def handler(req):
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0.2]}, {"index": 0, "embedding": [0.1]}]})
    assert _provider(handler).embed(["a", "b"]) == [[0.1], [0.2]]


def _use(monkeypatch, provider):
    monkeypatch.setattr(llm, "get_provider", lambda: provider)


def test_env_switch_routes_calls_and_traces_provider(monkeypatch, tmp_path):
    """Selecting openai_compat routes call_gemini to the local endpoint, and
    the traced call records provider, model, latency and tokens."""
    monkeypatch.setattr(gemini, "FIXTURE_DIR", tmp_path)

    def handler(req):
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "local answer"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 2}})
    _use(monkeypatch, _provider(handler))
    token = llm.begin_collecting()
    assert gemini.call_gemini("understand", "water issue") == "local answer"
    call = llm.end_collecting(token)[0]
    assert call["provider"] == "openai_compat" and call["model"] == "llama3.1"
    assert call["input_tokens"] == 7 and call["output_tokens"] == 2
    assert call["latency_ms"] >= 0
    # Non-Gemini fixtures live in their own namespace (never replayed as Gemini).
    stages = {json.loads(p.read_text())["stage"] for p in tmp_path.glob("*.json")}
    assert stages == {"understand@openai_compat/llama3.1"}


def test_get_provider_reads_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_BASE_URL", "http://local:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5")
    p = llm.get_provider()
    assert (p.name, p.model) == ("openai_compat", "qwen2.5")
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert llm.get_provider().name == "gemini"


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mystery")
    with pytest.raises(ValueError):
        llm.get_provider()
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    llm.get_provider()


def test_dimension_mismatch_refuses_and_writes_nothing(monkeypatch, tmp_path):
    def handler(req):
        return httpx.Response(200, json={"data": [{"index": 0,
                                                   "embedding": [0.0] * 1024}]})
    _use(monkeypatch, _provider(handler))
    assert "1024" in llm.check_embedding_dimension()
    with pytest.raises(EmbeddingDimensionMismatch):
        llm.embed("water")
    # Locate's cached embedder never writes a mismatched vector to disk.
    from app.stages import locate
    monkeypatch.setattr(locate, "FIXTURE_DIR", tmp_path)
    with pytest.raises(EmbeddingDimensionMismatch):
        locate._embedding_for("water", locate._live_embedder)
    assert not list(tmp_path.rglob("*.json"))


def test_matching_dimension_passes(monkeypatch):
    def handler(req):
        return httpx.Response(200, json={"data": [{"index": 0,
                                                   "embedding": [0.0] * 768}]})
    _use(monkeypatch, _provider(handler))
    assert llm.check_embedding_dimension() is None
