import json
import logging
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class LLMProviderConfig:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_provider: str = "local"
    providers: str = '{}'

    @field_validator("providers", mode="before")
    @classmethod
    def _coerce_empty_providers(cls, v: str) -> str:
        return v if v.strip() else '{}'

    def get_providers(self) -> dict[str, LLMProviderConfig]:
        raw = json.loads(self.providers)
        result = {}
        for name, cfg in raw.items():
            result[name] = LLMProviderConfig(
                base_url=cfg.get("base_url", "http://localhost:11434/v1"),
                api_key=cfg.get("api_key", "not-needed") or "not-needed",
                model=cfg.get("model", ""),
            )
        return result

    def get_provider(self, name: str | None = None) -> LLMProviderConfig:
        providers = self.get_providers()
        provider_name = name or self.default_provider
        if provider_name in providers:
            return providers[provider_name]
        if providers:
            return next(iter(providers.values()))
        return LLMProviderConfig(
            base_url="http://localhost:11434/v1",
            api_key="not-needed",
            model="qwen2.5:7b",
        )


class MCPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MCP_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server_urls: str = ""
    stdio_command: str = ""
    stdio_args: str = ""


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = "change-me-in-production"
    token_expire_hours: int = 24
    invite_codes: str = Field(default="", validation_alias=AliasChoices("AUTH_INVITE_CODES", "AUTH_INVITE_CODE"))
    cookie_name: str = "interviewlg_token"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    def get_invite_codes(self) -> list[str]:
        return [c.strip() for c in self.invite_codes.split(",") if c.strip()]


class AdminAuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ADMIN_AUTH_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secret_key: str = "change-me-admin-production"
    token_expire_hours: int = 8
    cookie_name: str = "interviewlg_admin_token"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"


class VectorDBSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VECTORDB_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://localhost:9000"


class RAGSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = True
    top_k: int = 3
    min_score: float = 0.65
    timeout_seconds: float = 3.0
    max_context_chars: int = 1800

    @field_validator("top_k")
    @classmethod
    def _validate_top_k(cls, value: int) -> int:
        return min(max(value, 1), 10)

    @field_validator("min_score")
    @classmethod
    def _validate_min_score(cls, value: float) -> float:
        return min(max(value, -1.0), 1.0)

    @field_validator("timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        return min(max(value, 0.2), 10.0)

    @field_validator("max_context_chars")
    @classmethod
    def _validate_max_context_chars(cls, value: int) -> int:
        return min(max(value, 200), 4000)


class ContextSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CONTEXT_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    window_tokens: int = 262144
    output_reserve_tokens: int = 16384
    input_budget_tokens: int = 196608
    tokenizer_encoding: str = "cl100k_base"
    recent_messages_trigger_tokens: int = 96000
    recent_messages_keep_tokens: int = 64000
    running_summary_max_tokens: int = 12000

    @field_validator("window_tokens")
    @classmethod
    def _validate_window(cls, value: int) -> int:
        return min(max(value, 4096), 262144)

    @field_validator("output_reserve_tokens")
    @classmethod
    def _validate_reserve(cls, value: int) -> int:
        return min(max(value, 512), 65536)

    @field_validator("input_budget_tokens")
    @classmethod
    def _validate_input_budget(cls, value: int) -> int:
        return min(max(value, 2048), 262144)

    @field_validator("recent_messages_trigger_tokens")
    @classmethod
    def _validate_recent_trigger(cls, value: int) -> int:
        return min(max(value, 1024), 262144)

    @field_validator("recent_messages_keep_tokens")
    @classmethod
    def _validate_recent_keep(cls, value: int) -> int:
        return min(max(value, 512), 262144)

    @field_validator("running_summary_max_tokens")
    @classmethod
    def _validate_summary_max(cls, value: int) -> int:
        return min(max(value, 256), 32768)


class QuestionRationaleSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QUESTION_RATIONALE_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = False


class SpeechSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SPEECH_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = "disabled"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "whisper-1"
    timeout_seconds: float = 30.0
    max_bytes: int = 10 * 1024 * 1024
    max_duration_seconds: int = 120
    allowed_mime_types: str = "audio/webm,audio/mp4,audio/mpeg,audio/wav,audio/x-wav,audio/ogg"
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_prefix: str = "interview-agent/speech"
    oss_url_expire_seconds: int = 300
    keep_temp_objects: bool = False

    def get_allowed_mime_types(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_mime_types.split(",") if item.strip()}

    @field_validator("timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: float) -> float:
        return min(max(value, 1.0), 120.0)

    @field_validator("max_bytes")
    @classmethod
    def _validate_max_bytes(cls, value: int) -> int:
        return min(max(value, 128 * 1024), 25 * 1024 * 1024)

    @field_validator("max_duration_seconds")
    @classmethod
    def _validate_max_duration(cls, value: int) -> int:
        return min(max(value, 5), 600)

    @field_validator("oss_url_expire_seconds")
    @classmethod
    def _validate_oss_url_expire(cls, value: int) -> int:
        return min(max(value, 60), 3600)


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SERVER_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:8000"

    def get_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


llm_settings = LLMSettings()
mcp_settings = MCPSettings()
auth_settings = AuthSettings()
admin_auth_settings = AdminAuthSettings()
vectordb_settings = VectorDBSettings()
rag_settings = RAGSettings()
context_settings = ContextSettings()
question_rationale_settings = QuestionRationaleSettings()
speech_settings = SpeechSettings()
server_settings = ServerSettings()


def _log_loaded_settings() -> None:
    try:
        provider = llm_settings.get_provider()
        masked = (provider.api_key[:8] + "...") if len(provider.api_key) > 8 else "***"
        logger.info(
            "settings loaded llm_provider=%s model=%s base_url=%s api_key=%s mcp_urls=%s vectordb=%s",
            llm_settings.default_provider, provider.model, provider.base_url, masked,
            mcp_settings.server_urls or "(none)", vectordb_settings.base_url,
        )
        logger.info(
            "rag settings enabled=%s top_k=%d min_score=%.2f timeout=%.1fs max_context_chars=%d",
            rag_settings.enabled,
            rag_settings.top_k,
            rag_settings.min_score,
            rag_settings.timeout_seconds,
            rag_settings.max_context_chars,
        )
        logger.info(
            "context settings window_tokens=%d input_budget_tokens=%d output_reserve_tokens=%d tokenizer=%s",
            context_settings.window_tokens,
            context_settings.input_budget_tokens,
            context_settings.output_reserve_tokens,
            context_settings.tokenizer_encoding,
        )
        logger.info(
            "context rolling summary trigger=%d keep=%d summary_max=%d",
            context_settings.recent_messages_trigger_tokens,
            context_settings.recent_messages_keep_tokens,
            context_settings.running_summary_max_tokens,
        )
        logger.info("question rationale debug enabled=%s", question_rationale_settings.enabled)
        logger.info(
            "speech settings provider=%s model=%s max_bytes=%d max_duration=%ds",
            speech_settings.provider,
            speech_settings.model,
            speech_settings.max_bytes,
            speech_settings.max_duration_seconds,
        )
    except Exception:
        logger.warning("failed to log loaded settings", exc_info=True)


_log_loaded_settings()
