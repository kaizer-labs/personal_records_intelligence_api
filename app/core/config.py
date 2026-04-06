from dataclasses import dataclass
import os


def _parse_origins(raw_value: str) -> list[str]:
    origins = [origin.strip() for origin in raw_value.split(",")]
    return [origin for origin in origins if origin]


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    app_env: str
    cors_origins: list[str]
    duckdb_path: str
    storage_root: str
    examples_path: str
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embedding_model: str
    ollama_chat_num_ctx: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", "Personal Records Intelligence API"),
            app_version=os.getenv("APP_VERSION", "0.1.0"),
            app_env=os.getenv("APP_ENV", "development"),
            cors_origins=_parse_origins(
                os.getenv("CORS_ORIGINS", "http://localhost:5173")
            ),
            duckdb_path=os.getenv("DUCKDB_PATH", "/app/data/duckdb/app.duckdb"),
            storage_root=os.getenv("STORAGE_ROOT", "/app/data/library"),
            examples_path=os.getenv("EXAMPLES_PATH", "/app/examples"),
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL", "http://host.docker.internal:11434"
            ),
            ollama_chat_model=os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b"),
            ollama_embedding_model=os.getenv(
                "OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"
            ),
            ollama_chat_num_ctx=int(os.getenv("OLLAMA_CHAT_NUM_CTX", "4096")),
        )


settings = Settings.from_env()
