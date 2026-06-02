from __future__ import annotations

import hashlib
import math
from typing import Protocol

from openai import OpenAI

from interview_vectordb.config import EmbeddingSettings


class EmbeddingProvider(Protocol):
    dimensions: int
    provider_name: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


class DeterministicEmbeddingProvider:
    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions
        self.provider_name = "deterministic"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [token for token in text.lower().replace("\n", " ").split(" ") if token]
        if not tokens:
            tokens = [text.lower()]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[idx] += sign
        return normalize_vector(vector)


class OpenAICompatibleEmbeddingProvider:
    def __init__(self, settings: EmbeddingSettings) -> None:
        if not settings.api_key.strip():
            raise ValueError("EMBEDDING_API_KEY is required for OpenAI-compatible embedding provider")
        self.settings = settings
        self.dimensions = settings.dimensions
        self.provider_name = f"{settings.provider}:{settings.model}"
        self._client = OpenAI(base_url=settings.base_url, api_key=settings.api_key)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self.settings.model,
            input=texts,
            dimensions=self.settings.dimensions,
            encoding_format="float",
        )
        rows = sorted(response.data, key=lambda item: item.index)
        return [normalize_vector(list(item.embedding)) for item in rows]


def build_embedding_provider(settings: EmbeddingSettings) -> EmbeddingProvider:
    provider = settings.provider.strip().lower()
    if provider in {"deterministic", "fake", "local"}:
        return DeterministicEmbeddingProvider(dimensions=settings.dimensions)
    if provider in {"dashscope", "openai", "openai-compatible", "siliconflow"}:
        return OpenAICompatibleEmbeddingProvider(settings)
    raise ValueError(f"Unsupported embedding provider: {settings.provider}")


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=False))
