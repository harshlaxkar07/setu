"""OpenAI-compatible provider (design D16): any server speaking the
`/v1/chat/completions` and `/v1/embeddings` protocol — a locally hosted model
(Ollama, vLLM, llama.cpp server), a government-approved gateway, or a
commercial endpoint. Plain httpx: no vendor SDK.
"""
import base64
import os

import httpx

from app.llm.base import Completion

DEFAULT_TIMEOUT_S = 120.0


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self, base_url: str, model: str, embed_model: str,
                 api_key: str | None = None, client: httpx.Client | None = None):
        if not base_url or not model:
            raise ValueError("openai_compat needs LLM_BASE_URL and LLM_MODEL")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model or model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.Client(timeout=DEFAULT_TIMEOUT_S)
        self._headers = headers

    @classmethod
    def from_env(cls) -> "OpenAICompatProvider":
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", ""),
            model=os.environ.get("LLM_MODEL", ""),
            embed_model=os.environ.get("EMBED_MODEL", ""),
            api_key=os.environ.get("LLM_API_KEY") or None,
        )

    def complete(self, prompt: str, image_bytes: bytes | None,
                 json_mode: bool = False) -> Completion:
        if image_bytes is not None:
            mime = "image/png" if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"}},
            ]
        else:
            content = prompt
        body = {"model": self.model,
                "messages": [{"role": "user", "content": content}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        resp = self._client.post(f"{self.base_url}/chat/completions",
                                 json=body, headers=self._headers)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        return Completion(
            data["choices"][0]["message"]["content"] or "",
            usage.get("prompt_tokens"), usage.get("completion_tokens"),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.post(f"{self.base_url}/embeddings",
                                 json={"model": self.embed_model, "input": texts},
                                 headers=self._headers)
        resp.raise_for_status()
        rows = sorted(resp.json()["data"], key=lambda r: r.get("index", 0))
        return [r["embedding"] for r in rows]
