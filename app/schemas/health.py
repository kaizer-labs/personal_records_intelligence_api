from typing import Literal

from pydantic import BaseModel


class DatabaseHealthResponse(BaseModel):
    status: Literal["ok"]
    engine: Literal["duckdb"]
    version: str
    path: str
    table_count: int


class HealthCheckResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    database: DatabaseHealthResponse
