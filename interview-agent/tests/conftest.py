import json
import os

os.environ.setdefault("LLM_DEFAULT_PROVIDER", "test")
os.environ.setdefault(
    "LLM_PROVIDERS",
    json.dumps(
        {
            "test": {
                "base_url": "http://localhost:1/v1",
                "api_key": "test-key",
                "model": "test-model",
            }
        }
    ),
)
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("ADMIN_AUTH_SECRET_KEY", "test-admin-secret-key-for-unit-tests-only")
os.environ.setdefault("MCP_SERVER_URLS", "")
os.environ.setdefault("VECTORDB_BASE_URL", "http://localhost:1")

import pytest


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    """Ensure no real .env is loaded during tests."""
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "test")
    monkeypatch.setenv(
        "LLM_PROVIDERS",
        json.dumps(
            {
                "test": {
                    "base_url": "http://localhost:1/v1",
                    "api_key": "test-key",
                    "model": "test-model",
                }
            }
        ),
    )
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key-for-unit-tests-only")
    monkeypatch.setenv("ADMIN_AUTH_SECRET_KEY", "test-admin-secret-key-for-unit-tests-only")
    monkeypatch.setenv("MCP_SERVER_URLS", "")
    monkeypatch.setenv("VECTORDB_BASE_URL", "http://localhost:1")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr("interview_agent.db._DB_PATH", data_dir / "interview.db")

    yield data_dir
