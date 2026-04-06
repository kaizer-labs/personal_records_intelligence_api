from typing import Literal

from pydantic import BaseModel


class DatabaseHealthResponse(BaseModel):
    status: Literal["ok"]
    engine: Literal["duckdb"]
    version: str
    path: str
    table_count: int


class OllamaHealthResponse(BaseModel):
    base_url: str
    chat_model: str
    embedding_model: str
    chat_num_ctx: int


class HealthCheckResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    database: DatabaseHealthResponse
    ollama: OllamaHealthResponse
