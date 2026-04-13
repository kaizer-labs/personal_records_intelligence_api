from __future__ import annotations

from pathlib import Path

import pytest

from app.db.connection import DatabaseManager


@pytest.fixture
def database(tmp_path: Path) -> DatabaseManager:
    database = DatabaseManager(str(tmp_path / "data" / "app.duckdb"))
    database.connect()
    try:
        yield database
    finally:
        database.close()
