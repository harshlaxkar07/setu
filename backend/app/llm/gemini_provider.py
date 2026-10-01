"""Gemini provider — the default (hackathon free tier)."""
from app.constants import EMBEDDING_DIM, EMBEDDING_MODEL, GEMINI_MODEL
from app.llm.base import Completion


class GeminiProvider:
    name = "gemini"
    model = GEMINI_MODEL
    embed_model = EMBEDDING_MODEL

    def complete(self, prompt: str, image_bytes: bytes | None,
                 json_mode: bool = False) -> Completion:
        # json_mode is implicit: schema-bound prompts already demand JSON.
        # Resolved at call time so tests that monkeypatch app.gemini._live_call
        # keep intercepting every live Gemini call.
        from app import gemini
        gemini._last_usage.set({})  # never report a previous call's usage
        text = gemini._live_call(prompt, image_bytes)
        usage = gemini._last_usage.get()
        return Completion(text, usage.get("input_tokens"), usage.get("output_tokens"))

    def embed(self, texts: list[str]) -> list[list[float]]:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        client = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
        # gemini-embedding-001 defaults to 3072 dims; the column is 768.
        if len(texts) == 1:
            return [client.embed_query(texts[0], output_dimensionality=EMBEDDING_DIM)]
        return client.embed_documents(texts, output_dimensionality=EMBEDDING_DIM)
