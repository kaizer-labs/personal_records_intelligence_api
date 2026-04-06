from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.connection import DatabaseManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    database = DatabaseManager(settings.duckdb_path)
    database.connect()
    app.state.db = database

    try:
        yield
    finally:
        database.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {
            "message": "Personal Records Intelligence API",
            "health_check_url": "/health_check",
            "docs_url": "/docs",
            "duckdb_path": settings.duckdb_path,
        }

    app.include_router(api_router)
    return app


app = create_app()
