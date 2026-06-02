import logging
import json
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://localhost:11434/v1"
    api_key: str = "not-needed"
    model: str = "qwen2.5:7b"
    default_provider: str = "local"
    providers: str = ""

    @field_validator("api_key", mode="before")
    @classmethod
    def _coerce_empty_key(cls, v: str) -> str:
        return v if v.strip() else "not-needed"

    @model_validator(mode="after")
    def _load_from_providers(self) -> "LLMSettings":
        if not self.providers.strip():
            return self
        try:
            providers = json.loads(self.providers)
            cfg = providers.get(self.default_provider)
            if cfg is None and providers:
                cfg = next(iter(providers.values()))
            if cfg:
                self.base_url = cfg.get("base_url", self.base_url)
                self.api_key = cfg.get("api_key", self.api_key) or "not-needed"
                self.model = cfg.get("model", self.model)
        except Exception:
            logger.warning("Failed to parse LLM_PROVIDERS for vectordb", exc_info=True)
        return self


class MCPServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MCP_SERVER_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = 9000


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    provider: str = "deterministic"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: str = ""
    model: str = "text-embedding-v4"
    dimensions: int = 1024
    batch_size: int = 10

    @field_validator("api_key", mode="before")
    @classmethod
    def _coerce_none_key(cls, v: str | None) -> str:
        return v or ""

    @field_validator("dimensions")
    @classmethod
    def _validate_dimensions(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("embedding dimensions must be positive")
        return v

    @field_validator("batch_size")
    @classmethod
    def _validate_batch_size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("embedding batch_size must be positive")
        return v


class VectorDBSecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VECTORDB_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    admin_token: str = ""
    cors_origins: str = ""

    def get_cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def _mask_api_key(key: str) -> str:
    if not key or key == "not-needed":
        return key
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"


llm_settings = LLMSettings()
embedding_settings = EmbeddingSettings()
mcp_server_settings = MCPServerSettings()
security_settings = VectorDBSecuritySettings()

logger.info(
    "Loaded LLMSettings: base_url=%s model=%s api_key=%s",
    llm_settings.base_url,
    llm_settings.model,
    _mask_api_key(llm_settings.api_key),
)
logger.info(
    "Loaded EmbeddingSettings: provider=%s base_url=%s model=%s dimensions=%d batch_size=%d api_key=%s",
    embedding_settings.provider,
    embedding_settings.base_url,
    embedding_settings.model,
    embedding_settings.dimensions,
    embedding_settings.batch_size,
    _mask_api_key(embedding_settings.api_key),
)
logger.info("Loaded MCPServerSettings: port=%d", mcp_server_settings.port)
