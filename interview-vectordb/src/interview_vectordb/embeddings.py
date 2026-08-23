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


class EmbeddingCompatibilityError(RuntimeError):
    """Raised when runtime query embeddings do not match persisted index embeddings."""


def build_embedding_readiness(
    provider: EmbeddingProvider,
    indexed_metadata: list[tuple[str, int, int]],
) -> dict:
    indexed_models = sorted({model for model, _, _ in indexed_metadata if model})
    indexed_dimensions = sorted({int(dimensions) for _, dimensions, _ in indexed_metadata})
    indexed_count = sum(int(count) for _, _, count in indexed_metadata)
    runtime_model = provider.provider_name
    runtime_dimensions = provider.dimensions
    ready = indexed_count == 0 or (
        indexed_models == [runtime_model] and indexed_dimensions == [runtime_dimensions]
    )
    reason = ""
    if not ready:
        reason = (
            "Embedding index is incompatible with the runtime provider: "
            f"runtime={runtime_model}/{runtime_dimensions}, "
            f"indexed={indexed_models}/{indexed_dimensions}."
        )
    return {
        "ready": ready,
        "runtime_model": runtime_model,
        "runtime_dimensions": runtime_dimensions,
        "indexed_models": indexed_models,
        "indexed_dimensions": indexed_dimensions,
        "indexed_count": indexed_count,
        "reason": reason,
    }


def require_embedding_compatibility(readiness: dict) -> None:
    if not readiness.get("ready"):
        raise EmbeddingCompatibilityError(str(readiness.get("reason") or "Embedding index is incompatible"))


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
