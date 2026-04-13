from pathlib import Path

from fastapi.testclient import TestClient

import app.api.v1.endpoints.health as health_endpoint
import app.main as app_main
from app.core.config import Settings


def test_health_check_returns_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Personal Records Intelligence API")
    monkeypatch.setenv("APP_VERSION", "0.1.0")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "data" / "duckdb" / "app.duckdb"))
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "data" / "library"))
    monkeypatch.setenv("EXAMPLES_PATH", str(tmp_path / "examples"))
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setenv("OLLAMA_CHAT_NUM_CTX", "4096")

    settings = Settings.from_env()
    monkeypatch.setattr(app_main, "settings", settings)
    monkeypatch.setattr(health_endpoint, "settings", settings)

    app = app_main.create_app()
    with TestClient(app) as client:
        response = client.get("/health_check")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == settings.app_name
    assert payload["version"] == settings.app_version
    assert payload["environment"] == settings.app_env
    assert payload["database"]["status"] == "ok"
    assert payload["database"]["engine"] == "duckdb"
    assert payload["database"]["path"] == settings.duckdb_path
    assert payload["database"]["table_count"] >= 1
    assert payload["ollama"]["base_url"] == settings.ollama_base_url
    assert payload["ollama"]["chat_model"] == settings.ollama_chat_model
    assert payload["ollama"]["embedding_model"] == settings.ollama_embedding_model
    assert payload["ollama"]["chat_num_ctx"] == settings.ollama_chat_num_ctx
