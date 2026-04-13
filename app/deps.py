from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.db.connection import DatabaseManager
from app.services.chat import ChatService
from app.services.library import LibraryService
from app.services.ollama import OllamaClient


def get_database(request: Request) -> DatabaseManager:
    return request.app.state.db


def get_ollama_client(request: Request) -> OllamaClient:
    return request.app.state.ollama_client


def get_library_service(request: Request) -> LibraryService:
    return request.app.state.library_service


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


DatabaseDep = Annotated[DatabaseManager, Depends(get_database)]
OllamaClientDep = Annotated[OllamaClient, Depends(get_ollama_client)]
LibraryServiceDep = Annotated[LibraryService, Depends(get_library_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
