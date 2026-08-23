import json

from interview_agent.config import (
    AuthSettings,
    ContextSettings,
    LLMSettings,
    MCPSettings,
    RAGSettings,
    ServerSettings,
    SpeechSettings,
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


def test_rag_settings_use_conservative_relevance_threshold(monkeypatch):
    monkeypatch.delenv("RAG_MIN_SCORE", raising=False)
    assert RAGSettings(_env_file=None).min_score == 0.65


def test_rag_settings_clamp_relevance_threshold(monkeypatch):
    monkeypatch.setenv("RAG_MIN_SCORE", "2")
    assert RAGSettings(_env_file=None).min_score == 1.0


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


def test_speech_settings_default_disabled(monkeypatch):
    for key in (
        "SPEECH_PROVIDER",
        "SPEECH_API_KEY",
        "SPEECH_BASE_URL",
        "SPEECH_MODEL",
        "SPEECH_MAX_BYTES",
        "SPEECH_MAX_DURATION_SECONDS",
        "SPEECH_OSS_ENDPOINT",
        "SPEECH_OSS_BUCKET",
        "SPEECH_KEEP_TEMP_OBJECTS",
    ):
        monkeypatch.delenv(key, raising=False)

    s = SpeechSettings(_env_file=None)
    assert s.provider == "disabled"
    assert s.model == "whisper-1"
    assert "audio/webm" in s.get_allowed_mime_types()
    assert s.keep_temp_objects is False


def test_speech_settings_clamps_limits(monkeypatch):
    monkeypatch.setenv("SPEECH_MAX_BYTES", "1")
    monkeypatch.setenv("SPEECH_MAX_DURATION_SECONDS", "9999")
    monkeypatch.setenv("SPEECH_TIMEOUT_SECONDS", "0.1")

    s = SpeechSettings(_env_file=None)
    assert s.max_bytes == 128 * 1024
    assert s.max_duration_seconds == 600
    assert s.timeout_seconds == 1.0


def test_speech_settings_oss_config(monkeypatch):
    monkeypatch.setenv("SPEECH_PROVIDER", "dashscope_file")
    monkeypatch.setenv("SPEECH_OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")
    monkeypatch.setenv("SPEECH_OSS_BUCKET", "bucket")
    monkeypatch.setenv("SPEECH_OSS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("SPEECH_OSS_ACCESS_KEY_SECRET", "sk")
    monkeypatch.setenv("SPEECH_OSS_URL_EXPIRE_SECONDS", "10")

    s = SpeechSettings(_env_file=None)
    assert s.provider == "dashscope_file"
    assert s.oss_endpoint == "oss-cn-hangzhou.aliyuncs.com"
    assert s.oss_bucket == "bucket"
    assert s.oss_url_expire_seconds == 60


def test_mcp_settings_default(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URLS", raising=False)
    monkeypatch.delenv("MCP_STDIO_COMMAND", raising=False)
    monkeypatch.delenv("MCP_STDIO_ARGS", raising=False)
    s = MCPSettings(_env_file=None)
    assert s.server_urls == ""
    assert s.stdio_command == ""
    assert s.stdio_args == ""
