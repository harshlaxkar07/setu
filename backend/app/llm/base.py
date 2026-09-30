"""Provider contract shared by every LLM backend (design D16)."""
from dataclasses import dataclass
from typing import Protocol


class EmbeddingDimensionMismatch(RuntimeError):
    """Provider vectors do not fit the vector(768) column — never stored."""


@dataclass
class Completion:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class Provider(Protocol):
    name: str           # "gemini", "openai_compat"
    model: str          # chat model
    embed_model: str    # embedding model

    def complete(self, prompt: str, image_bytes: bytes | None,
                 json_mode: bool = False) -> Completion: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...
