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
        )


settings = Settings.from_env()
