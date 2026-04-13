from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings, _parse_optional_int, _parse_origins
from app.db.connection import DatabaseManager


def test_config_helpers_and_settings_from_env(monkeypatch) -> None:
    assert _parse_origins(" http://a.test, ,http://b.test ") == [
        "http://a.test",
        "http://b.test",
    ]
    assert _parse_optional_int(None) is None
    assert _parse_optional_int("   ") is None
    assert _parse_optional_int("42") == 42

    for key in (
        "APP_NAME",
        "APP_VERSION",
        "APP_ENV",
        "CORS_ORIGINS",
        "DUCKDB_PATH",
        "STORAGE_ROOT",
        "EXAMPLES_PATH",
        "OLLAMA_BASE_URL",
        "OLLAMA_CHAT_MODEL",
        "OLLAMA_EMBEDDING_MODEL",
        "OLLAMA_CHAT_NUM_CTX",
        "OLLAMA_CHAT_NUM_PREDICT",
    ):
        monkeypatch.delenv(key, raising=False)

    defaults = Settings.from_env()
    assert defaults.app_name == "Personal Records Intelligence API"
    assert defaults.app_env == "development"
    assert defaults.cors_origins == ["http://localhost:5173"]
    assert defaults.ollama_chat_num_predict is None

    monkeypatch.setenv("APP_NAME", "PRI Test API")
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, http://localhost:5173")
    monkeypatch.setenv("DUCKDB_PATH", "/tmp/app.duckdb")
    monkeypatch.setenv("STORAGE_ROOT", "/tmp/storage")
    monkeypatch.setenv("EXAMPLES_PATH", "/tmp/examples")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "qwen:test")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "embed:test")
    monkeypatch.setenv("OLLAMA_CHAT_NUM_CTX", "8192")
    monkeypatch.setenv("OLLAMA_CHAT_NUM_PREDICT", "256")

    custom = Settings.from_env()
    assert custom.app_name == "PRI Test API"
    assert custom.app_version == "9.9.9"
    assert custom.app_env == "test"
    assert custom.cors_origins == ["http://localhost:3000", "http://localhost:5173"]
    assert custom.duckdb_path == "/tmp/app.duckdb"
    assert custom.storage_root == "/tmp/storage"
    assert custom.examples_path == "/tmp/examples"
    assert custom.ollama_base_url == "http://127.0.0.1:11434"
    assert custom.ollama_chat_model == "qwen:test"
    assert custom.ollama_embedding_model == "embed:test"
    assert custom.ollama_chat_num_ctx == 8192
    assert custom.ollama_chat_num_predict == 256


def test_database_manager_round_trip_and_health(database: DatabaseManager) -> None:
    database.execute(
        "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
        ["custom_key", "custom_value"],
    )

    row = database.fetchone(
        "SELECT value FROM app_metadata WHERE key = ?",
        ["custom_key"],
    )
    assert row == ("custom_value",)

    rows = database.fetchall(
        "SELECT key FROM app_metadata WHERE key IN (?, ?) ORDER BY key ASC",
        ["bootstrap_status", "custom_key"],
    )
    assert rows == [("bootstrap_status",), ("custom_key",)]

    health = database.health()
    assert health.status == "ok"
    assert health.engine == "duckdb"
    assert health.path.endswith("app.duckdb")
    assert health.table_count >= 6
    assert health.version


def test_database_manager_requires_connection_and_close_is_safe(tmp_path: Path) -> None:
    database = DatabaseManager(str(tmp_path / "other" / "app.duckdb"))

    with pytest.raises(RuntimeError, match="has not been initialized"):
        _ = database.connection

    database.close()
    database.connect()
    assert database.connection is not None
    database.close()
    database.close()

