import pytest

from interview_vectordb.config import EmbeddingSettings
from interview_vectordb.embeddings import DeterministicEmbeddingProvider, build_embedding_provider, cosine_similarity


def test_deterministic_embedding_provider_is_stable():
    provider = DeterministicEmbeddingProvider(dimensions=16)

    left = provider.embed_texts(["redis zset 跳表"])[0]
    right = provider.embed_texts(["redis zset 跳表"])[0]

    assert provider.provider_name == "deterministic"
    assert left == right
    assert len(left) == 16
    assert cosine_similarity(left, right) == pytest.approx(1.0)


def test_build_embedding_provider_default_fake():
    provider = build_embedding_provider(EmbeddingSettings(_env_file=None, dimensions=32))

    assert isinstance(provider, DeterministicEmbeddingProvider)
    assert provider.dimensions == 32
