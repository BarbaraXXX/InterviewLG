from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str
    temperature: float
    timeout_seconds: float


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_llm_settings(root: Path) -> LLMSettings:
    load_dotenv(root / ".env")
    base_url = (
        os.getenv("CODING_LLM_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or "https://api.deepseek.com"
    )
    api_key = os.getenv("CODING_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY") or ""
    model = os.getenv("CODING_LLM_MODEL") or os.getenv("DEEPSEEK_MODEL") or os.getenv("LLM_MODEL") or "deepseek-chat"
    temperature = _float_env("CODING_LLM_TEMPERATURE", 0.2)
    timeout_seconds = _float_env("CODING_LLM_TIMEOUT_SECONDS", 60.0)
    if not api_key:
        raise RuntimeError("CODING_LLM_API_KEY is required. Put it in coding-problems/.env or export it.")
    return LLMSettings(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default
