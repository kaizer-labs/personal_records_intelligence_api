from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as app_main
from app.api.router import api_router
from app.core.config import Settings
from app.schemas.chat import (
    ChatConversationDetailResponse,
    ChatConversationListResponse,
    ChatConversationSummary,
    ChatMessage,
    ChatResponse,
    ChatSource,
)
from app.schemas.health import DatabaseHealthResponse
from app.schemas.library import (
    DocumentSummary,
    FolderListResponse,
    FolderSummary,
    FolderSyncResponse,
    ProcessedFileResult,
)
from app.services.library import IngestFile, StoredDocumentFile
from app.services.ollama import OllamaServiceError


class FakeDatabase:
    def health(self) -> DatabaseHealthResponse:
        return DatabaseHealthResponse(
            status="ok",
            engine="duckdb",
            version="test-version",
            path="/tmp/test.duckdb",
            table_count=7,
        )


class FakeLibraryService:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.upload_batches: list[list[IngestFile]] = []
        self.deleted_documents: list[str] = []
        self.cleared_folders: list[str] = []

    def list_folders(self) -> FolderListResponse:
        return FolderListResponse(
            folders=[
                FolderSummary(
                    name="Finance",
                    origin="browser_upload",
                    updated_at="2026-04-12T10:00:00",
                    document_count=1,
                    chunk_count=3,
                    documents=[
                        DocumentSummary(
                            id="doc-1",
                            filename="statement.txt",
                            relative_path="statement.txt",
                            media_type="text/plain",
                            char_count=42,
                            chunk_count=3,
                            updated_at="2026-04-12T10:00:00",
                        )
                    ],
                )
            ]
        )

    def sync_example_files(self) -> FolderSyncResponse:
        return FolderSyncResponse(
            folders=self.list_folders().folders,
            processed_files=[
                ProcessedFileResult(
                    folder_name="Examples",
                    relative_path="example.txt",
                    filename="example.txt",
                    status="ingested",
                    document_id="doc-1",
                    char_count=12,
                    chunk_count=1,
                )
            ],
        )

    def sync_browser_uploads(self, files: list[IngestFile]) -> FolderSyncResponse:
        self.upload_batches.append(files)
        return FolderSyncResponse(
            folders=self.list_folders().folders,
            processed_files=[
                ProcessedFileResult(
                    folder_name="Finance",
                    relative_path=file.relative_path,
                    filename=file.filename,
                    status="ingested",
                    document_id=f"doc-{index}",
                    char_count=len(file.data),
                    chunk_count=1,
                )
                for index, file in enumerate(files, start=1)
            ],
        )

    def remove_document(self, document_id: str) -> FolderListResponse:
        self.deleted_documents.append(document_id)
        return self.list_folders()

    def get_document_file(self, document_id: str) -> StoredDocumentFile | None:
        if document_id == "missing":
            return None
        return StoredDocumentFile(
            document_id=document_id,
            filename="statement.txt",
            media_type="text/plain",
            storage_path=self.file_path,
        )

    def clear_folder(self, folder_name: str) -> FolderListResponse:
        self.cleared_folders.append(folder_name)
        return FolderListResponse(folders=[])


class FakeChatService:
    def __init__(self) -> None:
        self.deleted_conversations: list[str] = []

    def list_conversations(self) -> ChatConversationListResponse:
        return ChatConversationListResponse(
            conversations=[
                ChatConversationSummary(
                    id="conv-1",
                    title="Subscription review",
                    folder_names=["Finance"],
                    updated_at="2026-04-12T10:00:00",
                    message_count=2,
                    preview="The gym renews on January 15.",
                )
            ]
        )

    def get_conversation(self, conversation_id: str) -> ChatConversationDetailResponse | None:
        if conversation_id == "missing":
            return None
        return ChatConversationDetailResponse(
            conversation=self.list_conversations().conversations[0],
            messages=[
                ChatMessage(
                    id="msg-1",
                    role="assistant",
                    content="The gym renews on January 15.",
                    sources=[
                        ChatSource(
                            document_id="doc-1",
                            folder_name="Finance",
                            document_name="gym.pdf",
                            relative_path="gym.pdf",
                            excerpt="Renewal date January 15.",
                            score=4.8,
                        )
                    ],
                    created_at="2026-04-12T10:00:01",
                )
            ],
        )

    def delete_conversation(self, conversation_id: str) -> ChatConversationListResponse:
        self.deleted_conversations.append(conversation_id)
        return self.list_conversations()

    def answer_question(
        self,
        *,
        question: str,
        folder_names: list[str],
        conversation_id: str | None = None,
    ) -> ChatResponse:
        if question == "fail":
            raise OllamaServiceError("Ollama unavailable")
        return ChatResponse(
            conversation_id=conversation_id or "conv-1",
            conversation_title="Subscription review",
            answer=f"Answer for {question}",
            model="chat-model",
            selected_folders=folder_names,
            sources=[],
        )

    def stream_answer_question(
        self,
        *,
        question: str,
        folder_names: list[str],
        conversation_id: str | None = None,
    ):
        del conversation_id
        del folder_names
        yield '{"type":"start","conversation_id":"conv-1"}\n'
        yield f'{{"type":"delta","delta":"{question}"}}\n'
        yield '{"type":"final","answer":"done"}\n'


def build_test_app(file_path: Path) -> FastAPI:
    app = FastAPI()
    app.state.db = FakeDatabase()
    app.state.library_service = FakeLibraryService(file_path)
    app.state.chat_service = FakeChatService()
    app.include_router(api_router)
    return app


def test_api_endpoints_use_app_state_services(tmp_path: Path) -> None:
    file_path = tmp_path / "statement.txt"
    file_path.write_text("stored text", encoding="utf-8")

    app = build_test_app(file_path)
    with TestClient(app) as client:
        folders_response = client.get("/api/library/folders")
        assert folders_response.status_code == 200
        assert folders_response.json()["folders"][0]["name"] == "Finance"

        examples_response = client.post("/api/library/examples/sync")
        assert examples_response.status_code == 200
        assert examples_response.json()["processed_files"][0]["status"] == "ingested"

        upload_response = client.post(
            "/api/library/folders/upload",
            files=[
                (
                    "files",
                    ("Finance/invoice.txt", b"invoice data", "text/plain"),
                )
            ],
        )
        assert upload_response.status_code == 200
        assert (
            upload_response.json()["processed_files"][0]["relative_path"]
            == "Finance/invoice.txt"
        )

        download_response = client.get("/api/library/documents/doc-1/file")
        assert download_response.status_code == 200
        assert download_response.content == b"stored text"

        missing_download = client.get("/api/library/documents/missing/file")
        assert missing_download.status_code == 404

        delete_document = client.delete("/api/library/documents/doc-1")
        assert delete_document.status_code == 200

        clear_folder = client.delete("/api/library/folders/Finance%20Folder")
        assert clear_folder.status_code == 200

        conversations = client.get("/api/chat/conversations")
        assert conversations.status_code == 200
        assert conversations.json()["conversations"][0]["id"] == "conv-1"

        conversation = client.get("/api/chat/conversations/conv-1")
        assert conversation.status_code == 200
        assert conversation.json()["messages"][0]["sources"][0]["document_name"] == "gym.pdf"

        missing_conversation = client.get("/api/chat/conversations/missing")
        assert missing_conversation.status_code == 404

        delete_conversation = client.delete("/api/chat/conversations/conv-1")
        assert delete_conversation.status_code == 200

        answer = client.post(
            "/api/chat/answers",
            json={"question": "What renews next?", "folder_names": ["Finance"]},
        )
        assert answer.status_code == 200
        assert answer.json()["answer"] == "Answer for What renews next?"

        answer_error = client.post(
            "/api/chat/answers",
            json={"question": "fail", "folder_names": []},
        )
        assert answer_error.status_code == 503
        assert answer_error.json()["detail"] == "Ollama unavailable"

        stream_response = client.post(
            "/api/chat/answers/stream",
            json={"question": "stream me", "folder_names": []},
        )
        assert stream_response.status_code == 200
        assert '"type":"delta"' in stream_response.text


def test_create_app_root_reflects_current_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "PRI API")
    monkeypatch.setenv("APP_VERSION", "0.1.0")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("DUCKDB_PATH", str(tmp_path / "data" / "app.duckdb"))
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "storage"))
    monkeypatch.setenv("EXAMPLES_PATH", str(tmp_path / "examples"))
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "chat-model")
    monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "embed-model")
    monkeypatch.setenv("OLLAMA_CHAT_NUM_CTX", "4096")

    settings = Settings.from_env()
    monkeypatch.setattr(app_main, "settings", settings)

    app = app_main.create_app()
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Personal Records Intelligence API"
    assert payload["health_check_url"] == "/health_check"
    assert payload["duckdb_path"] == settings.duckdb_path
    assert payload["storage_root"] == settings.storage_root
    assert payload["examples_path"] == settings.examples_path
    assert payload["ollama_base_url"] == settings.ollama_base_url
    assert payload["ollama_chat_model"] == settings.ollama_chat_model
    assert payload["ollama_embedding_model"] == settings.ollama_embedding_model


def test_dependency_helpers_return_app_state_objects() -> None:
    from fastapi import Request

    from app import deps

    app = FastAPI()
    app.state.db = object()
    app.state.ollama_client = object()
    app.state.library_service = object()
    app.state.chat_service = object()

    request = Request(
        {
            "type": "http",
            "app": app,
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        }
    )

    assert deps.get_database(request) is app.state.db
    assert deps.get_ollama_client(request) is app.state.ollama_client
    assert deps.get_library_service(request) is app.state.library_service
    assert deps.get_chat_service(request) is app.state.chat_service
