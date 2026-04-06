from __future__ import annotations

from pathlib import Path
import threading

import duckdb

from app.schemas.health import DatabaseHealthResponse


BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS app_metadata (
    key VARCHAR PRIMARY KEY,
    value VARCHAR,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS folders (
    id VARCHAR PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL,
    origin VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR PRIMARY KEY,
    folder_id VARCHAR NOT NULL,
    filename VARCHAR NOT NULL,
    relative_path VARCHAR NOT NULL,
    storage_path VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    extracted_text VARCHAR NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(folder_id, relative_path)
);

CREATE TABLE IF NOT EXISTS chunks (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL,
    chunk_index INTEGER NOT NULL,
    text VARCHAR NOT NULL,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, chunk_index)
);

DELETE FROM app_metadata WHERE key IN ('bootstrap_status', 'schema_version');

INSERT INTO app_metadata (key, value)
VALUES
    ('bootstrap_status', 'ready'),
    ('schema_version', '2');
"""


class DatabaseManager:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._lock = threading.Lock()

    def connect(self) -> duckdb.DuckDBPyConnection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = duckdb.connect(str(self.database_path))
        self.initialize()
        return self._connection

    def initialize(self) -> None:
        with self._lock:
            connection = self.connection
            connection.execute(BOOTSTRAP_SQL)

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._connection is None:
            raise RuntimeError("DuckDB connection has not been initialized.")
        return self._connection

    def health(self) -> DatabaseHealthResponse:
        with self._lock:
            version = self.connection.execute("SELECT version()").fetchone()
            table_count = self.connection.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'main'
                """
            ).fetchone()

        return DatabaseHealthResponse(
            status="ok",
            engine="duckdb",
            version=str(version[0]) if version else "unknown",
            path=str(self.database_path),
            table_count=int(table_count[0]) if table_count else 0,
        )

    def execute(self, query: str, params: list[object] | None = None) -> None:
        with self._lock:
            self.connection.execute(query, params or [])

    def fetchone(
        self,
        query: str,
        params: list[object] | None = None,
    ) -> tuple[object, ...] | None:
        with self._lock:
            return self.connection.execute(query, params or []).fetchone()

    def fetchall(
        self,
        query: str,
        params: list[object] | None = None,
    ) -> list[tuple[object, ...]]:
        with self._lock:
            return self.connection.execute(query, params or []).fetchall()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
