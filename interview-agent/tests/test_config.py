import json

from interview_agent.config import (
    AuthSettings,
    ContextSettings,
    LLMSettings,
    MCPSettings,
    ServerSettings,
    VectorDBSettings,
)


def test_llm_settings_from_env(monkeypatch):
    monkeypatch.setenv(
        "LLM_PROVIDERS",
        json.dumps(
            {
                "p1": {"base_url": "http://a", "api_key": "k1", "model": "m1"},
                "p2": {"base_url": "http://b", "api_key": "k2", "model": "m2"},
            }
        ),
    )
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "p1")
    s = LLMSettings()
    providers = s.get_providers()
    assert set(providers.keys()) == {"p1", "p2"}
    assert providers["p1"].model == "m1"


def test_llm_settings_default_provider(monkeypatch):
    monkeypatch.setenv(
        "LLM_PROVIDERS",
        json.dumps({"p1": {"base_url": "http://a", "api_key": "k1", "model": "m1"}}),
    )
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "p1")
    s = LLMSettings()
    p = s.get_provider()
    assert p.model == "m1"


def test_llm_settings_named_provider(monkeypatch):
    monkeypatch.setenv(
        "LLM_PROVIDERS",
        json.dumps(
            {
                "local": {"base_url": "http://l", "api_key": "kl", "model": "ml"},
                "deepseek": {"base_url": "http://d", "api_key": "kd", "model": "md"},
            }
        ),
    )
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "local")
    s = LLMSettings()
    p = s.get_provider("deepseek")
    assert p.model == "md"


def test_llm_settings_fallback(monkeypatch):
    monkeypatch.setenv(
        "LLM_PROVIDERS",
        json.dumps({"only": {"base_url": "http://o", "api_key": "ko", "model": "mo"}}),
    )
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "missing")
    s = LLMSettings()
    p = s.get_provider("absent")
    assert p.model == "mo"


def test_llm_settings_empty_providers(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "{}")
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "x")
    s = LLMSettings()
    p = s.get_provider()
    assert p.model == "qwen2.5:7b"
    assert p.base_url == "http://localhost:11434/v1"


def test_llm_settings_coerce_empty(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "   \n\t  ")
    s = LLMSettings()
    assert s.providers == "{}"
    assert s.get_providers() == {}


def test_auth_settings_default(monkeypatch):
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    monkeypatch.delenv("AUTH_TOKEN_EXPIRE_HOURS", raising=False)
    s = AuthSettings(_env_file=None)
    assert s.secret_key == "change-me-in-production"
    assert s.token_expire_hours == 24


def test_vectordb_settings_default(monkeypatch):
    monkeypatch.delenv("VECTORDB_BASE_URL", raising=False)
    s = VectorDBSettings(_env_file=None)
    assert s.base_url == "http://localhost:9000"


def test_server_settings_default(monkeypatch):
    monkeypatch.delenv("SERVER_HOST", raising=False)
    monkeypatch.delenv("SERVER_PORT", raising=False)
    s = ServerSettings(_env_file=None)
    assert s.host == "0.0.0.0"
    assert s.port == 8000


def test_server_settings_from_env(monkeypatch):
    monkeypatch.setenv("SERVER_HOST", "127.0.0.1")
    monkeypatch.setenv("SERVER_PORT", "8001")
    s = ServerSettings(_env_file=None)
    assert s.host == "127.0.0.1"
    assert s.port == 8001


def test_context_settings_default_uses_256k_budget(monkeypatch):
    for key in (
        "CONTEXT_WINDOW_TOKENS",
        "CONTEXT_OUTPUT_RESERVE_TOKENS",
        "CONTEXT_INPUT_BUDGET_TOKENS",
        "CONTEXT_RECENT_MESSAGES_TRIGGER_TOKENS",
        "CONTEXT_RECENT_MESSAGES_KEEP_TOKENS",
        "CONTEXT_RUNNING_SUMMARY_MAX_TOKENS",
    ):
        monkeypatch.delenv(key, raising=False)

    s = ContextSettings(_env_file=None)
    assert s.window_tokens == 262144
    assert s.output_reserve_tokens == 16384
    assert s.input_budget_tokens == 196608
    assert s.recent_messages_trigger_tokens == 96000
    assert s.recent_messages_keep_tokens == 64000
    assert s.running_summary_max_tokens == 12000


def test_context_settings_clamps_to_256k_ceiling(monkeypatch):
    monkeypatch.setenv("CONTEXT_WINDOW_TOKENS", "1048576")
    monkeypatch.setenv("CONTEXT_INPUT_BUDGET_TOKENS", "1048576")
    monkeypatch.setenv("CONTEXT_RECENT_MESSAGES_TRIGGER_TOKENS", "1048576")
    monkeypatch.setenv("CONTEXT_RECENT_MESSAGES_KEEP_TOKENS", "1048576")

    s = ContextSettings(_env_file=None)
    assert s.window_tokens == 262144
    assert s.input_budget_tokens == 262144
    assert s.recent_messages_trigger_tokens == 262144
    assert s.recent_messages_keep_tokens == 262144


def test_mcp_settings_default(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URLS", raising=False)
    monkeypatch.delenv("MCP_STDIO_COMMAND", raising=False)
    monkeypatch.delenv("MCP_STDIO_ARGS", raising=False)
    s = MCPSettings(_env_file=None)
    assert s.server_urls == ""
    assert s.stdio_command == ""
    assert s.stdio_args == ""
