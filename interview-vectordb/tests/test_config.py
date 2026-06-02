

import json


def test_llm_settings_defaults(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    from interview_vectordb.config import LLMSettings

    s = LLMSettings(_env_file=None)
    assert s.base_url == "http://localhost:11434/v1"
    assert s.api_key == "not-needed"
    assert s.model == "qwen2.5:7b"


def test_llm_settings_from_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("LLM_API_KEY", "sk-abc123")
    monkeypatch.setenv("LLM_MODEL", "my-model")

    from interview_vectordb.config import LLMSettings

    s = LLMSettings(_env_file=None)
    assert s.base_url == "https://api.example.com"
    assert s.api_key == "sk-abc123"
    assert s.model == "my-model"


def test_llm_settings_coerce_empty_key(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "   ")

    from interview_vectordb.config import LLMSettings

    s = LLMSettings(_env_file=None)
    assert s.api_key == "not-needed"


def test_llm_settings_from_providers(monkeypatch):
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "deepseek")
    monkeypatch.setenv(
        "LLM_PROVIDERS",
        json.dumps(
            {
                "local": {"base_url": "http://local/v1", "api_key": "", "model": "local-model"},
                "deepseek": {"base_url": "https://api.deepseek.com/v1", "api_key": "sk-test", "model": "deepseek-chat"},
            }
        ),
    )

    from interview_vectordb.config import LLMSettings

    s = LLMSettings(_env_file=None)
    assert s.base_url == "https://api.deepseek.com/v1"
    assert s.api_key == "sk-test"
    assert s.model == "deepseek-chat"


def test_mcp_server_settings_default_port(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_PORT", raising=False)

    from interview_vectordb.config import MCPServerSettings

    s = MCPServerSettings(_env_file=None)
    assert s.port == 9000


def test_embedding_settings_defaults(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_DIMENSIONS", raising=False)
    monkeypatch.delenv("EMBEDDING_BATCH_SIZE", raising=False)

    from interview_vectordb.config import EmbeddingSettings

    s = EmbeddingSettings(_env_file=None)
    assert s.provider == "deterministic"
    assert s.model == "text-embedding-v4"
    assert s.dimensions == 1024


def test_embedding_settings_from_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "dashscope")
    monkeypatch.setenv("EMBEDDING_API_KEY", "sk-test")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "512")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "5")

    from interview_vectordb.config import EmbeddingSettings

    s = EmbeddingSettings(_env_file=None)
    assert s.provider == "dashscope"
    assert s.api_key == "sk-test"
    assert s.dimensions == 512
    assert s.batch_size == 5
