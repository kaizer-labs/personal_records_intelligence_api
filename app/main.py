from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.connection import DatabaseManager
from app.repositories import ConversationRepository, DocumentRepository
from app.services.chat import ChatService
from app.services.library import LibraryService
from app.services.ollama import OllamaClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    database = DatabaseManager(settings.duckdb_path)
    database.connect()
    app.state.db = database

    ollama_client = OllamaClient(settings)
    app.state.ollama_client = ollama_client

    document_repository = DocumentRepository(database)
    conversation_repository = ConversationRepository(database)

    app.state.library_service = LibraryService(
        document_repository,
        ollama_client,
        storage_root=settings.storage_root,
        examples_root=settings.examples_path,
    )
    app.state.chat_service = ChatService(
        conversation_repository,
        app.state.library_service,
        ollama_client,
    )

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
            "storage_root": settings.storage_root,
            "examples_path": settings.examples_path,
            "ollama_base_url": settings.ollama_base_url,
            "ollama_chat_model": settings.ollama_chat_model,
            "ollama_embedding_model": settings.ollama_embedding_model,
        }

    app.include_router(api_router)
    return app


app = create_app()
