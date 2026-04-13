from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from app.db.connection import DatabaseManager
from app.repositories.documents import DocumentRepository
from app.services.library import IngestFile, LibraryService
from app.services.ollama import OllamaServiceError


class FakeLibraryOllamaClient:
    def __init__(
        self,
        *,
        embedding_model: str = "embed-model",
        embeddings: list[list[float]] | None = None,
        should_fail: bool = False,
    ) -> None:
        self.embedding_model = embedding_model
        self._embeddings = embeddings
        self._should_fail = should_fail
        self.embed_calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls.append(texts)
        if self._should_fail:
            raise OllamaServiceError("embeddings unavailable")
        if self._embeddings is not None:
            return self._embeddings
        return [[float(index + 1), float(len(text))] for index, text in enumerate(texts)]


def build_library_service(
    database: DatabaseManager,
    tmp_path: Path,
    ollama_client: FakeLibraryOllamaClient | None = None,
) -> LibraryService:
    storage_root = tmp_path / "storage"
    examples_root = tmp_path / "examples"
    storage_root.mkdir(parents=True, exist_ok=True)
    examples_root.mkdir(parents=True, exist_ok=True)
    return LibraryService(
        DocumentRepository(database),
        ollama_client or FakeLibraryOllamaClient(),
        storage_root=str(storage_root),
        examples_root=str(examples_root),
    )


def test_sync_browser_uploads_and_manage_documents(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    service = build_library_service(database, tmp_path)

    response = service.sync_browser_uploads(
        [
            IngestFile(
                relative_path="Finance/statement.txt",
                filename="statement.txt",
                content_type="text/plain",
                data=b"Monthly charge $12.00\n\nRenewal date January 15, 2026.",
            ),
            IngestFile(
                relative_path="Finance/details.json",
                filename="details.json",
                content_type="application/json",
                data=b'{"amount": 19.95, "renewal": "2026-02-01"}',
            ),
            IngestFile(
                relative_path="Finance/ignored.exe",
                filename="ignored.exe",
                content_type="application/octet-stream",
                data=b"binary",
            ),
            IngestFile(
                relative_path="Finance/empty.txt",
                filename="empty.txt",
                content_type="text/plain",
                data=b"  \n\t  ",
            ),
        ]
    )

    statuses = {item.relative_path: item.status for item in response.processed_files}
    assert statuses == {
        "statement.txt": "ingested",
        "details.json": "ingested",
        "ignored.exe": "skipped",
        "empty.txt": "skipped",
    }

    folders = service.list_folders().folders
    assert len(folders) == 1
    assert folders[0].name == "Finance"
    assert folders[0].document_count == 2
    assert folders[0].chunk_count >= 2

    chunks = service.search_chunks(folder_names=["Finance"])
    assert len(chunks) >= 2
    assert chunks[0].embedding_model == "embed-model"
    assert isinstance(chunks[0].embedding, list)

    document_id = response.processed_files[0].document_id
    assert document_id is not None
    stored_file = service.get_document_file(document_id)
    assert stored_file is not None
    assert stored_file.storage_path.is_file()

    service.remove_document("missing-document")
    after_delete = service.remove_document(document_id)
    assert after_delete.folders[0].document_count == 1

    cleared = service.clear_folder("Finance")
    assert cleared.folders == []


def test_sync_example_files_prunes_missing_documents(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    service = build_library_service(database, tmp_path)
    examples_root = Path(service._examples_root)

    (examples_root / "keep.txt").write_text("Keep me", encoding="utf-8")
    (examples_root / "remove.md").write_text("Remove me later", encoding="utf-8")
    (examples_root / ".ignored.txt").write_text("ignore", encoding="utf-8")
    (examples_root / "skip.png").write_bytes(b"png")

    first_sync = service.sync_example_files()
    assert {item.filename for item in first_sync.processed_files} == {"keep.txt", "remove.md"}
    assert service.list_folders().folders[0].document_count == 2

    (examples_root / "remove.md").unlink()
    second_sync = service.sync_example_files()
    assert {item.filename for item in second_sync.processed_files} == {"keep.txt"}
    assert service.list_folders().folders[0].document_count == 1


def test_extract_text_pdf_branch_and_embedding_failure(
    database: DatabaseManager,
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = build_library_service(
        database,
        tmp_path,
        ollama_client=FakeLibraryOllamaClient(should_fail=True),
    )

    class FakePdfPage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakePdfReader:
        def __init__(self, _buffer) -> None:
            self.pages = [FakePdfPage("Page one"), FakePdfPage("Page two")]

    monkeypatch.setattr("app.services.library.PdfReader", FakePdfReader)

    pdf_response = service.sync_browser_uploads(
        [
            IngestFile(
                relative_path="Scans/scan.pdf",
                filename="scan.pdf",
                content_type="application/pdf",
                data=b"%PDF-pretend",
            )
        ]
    )
    assert pdf_response.processed_files[0].status == "ingested"

    chunks = service.search_chunks(folder_names=["Scans"])
    assert len(chunks) >= 1
    assert all(chunk.embedding is None for chunk in chunks)


def test_document_file_validation_and_small_helpers(
    database: DatabaseManager,
    tmp_path: Path,
) -> None:
    service = build_library_service(database, tmp_path)
    repository = service._documents

    folder_id = repository.upsert_folder("Outside", "browser_upload")
    outside_path = tmp_path / "outside.txt"
    outside_path.write_text("outside", encoding="utf-8")
    outside_document_id = repository.upsert_document(
        folder_id=folder_id,
        filename="outside.txt",
        relative_path="outside.txt",
        storage_path=str(outside_path),
        media_type="text/plain",
        sha256="hash",
        extracted_text="outside",
        char_count=7,
        chunk_count=1,
    )

    assert service.get_document_file("missing") is None
    assert service.get_document_file(outside_document_id) is None
    assert service._slugify("  Team Contract (Final)!  ") == "team-contract-final"
    assert service._slugify("   ") == "document"
    assert service._serialize_timestamp(datetime(2026, 4, 12, 9, 30, 0)) == "2026-04-12T09:30:00"
    assert service._serialize_timestamp("raw") == "raw"

