from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import re
from uuid import uuid4

from pypdf import PdfReader

from app.repositories.documents import DocumentRepository
from app.schemas.library import (
    DocumentSummary,
    FolderListResponse,
    FolderSummary,
    FolderSyncResponse,
    ProcessedFileResult,
)
from app.services.ollama import OllamaClient, OllamaServiceError
from app.services.text_processing import chunk_text, normalize_text


SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
}


@dataclass(frozen=True)
class IngestFile:
    relative_path: str
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    document_id: str
    folder_name: str
    document_name: str
    relative_path: str
    text: str
    chunk_index: int
    embedding: list[float] | None
    embedding_model: str | None


@dataclass(frozen=True)
class StoredDocumentFile:
    document_id: str
    filename: str
    media_type: str
    storage_path: Path


class LibraryService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        ollama_client: OllamaClient,
        *,
        storage_root: str,
        examples_root: str,
    ) -> None:
        self._documents = document_repository
        self._ollama_client = ollama_client
        self._storage_root = Path(storage_root)
        self._examples_root = Path(examples_root)

    def list_folders(self) -> FolderListResponse:
        folder_rows = self._documents.list_folders()
        document_rows = self._documents.list_documents()

        documents_by_folder: dict[str, list[DocumentSummary]] = {}
        chunk_counts: dict[str, int] = {}

        for row in document_rows:
            folder_name = row.folder_name
            document = DocumentSummary(
                id=row.document_id,
                filename=row.filename,
                relative_path=row.relative_path,
                media_type=row.media_type,
                char_count=row.char_count,
                chunk_count=row.chunk_count,
                updated_at=self._serialize_timestamp(row.updated_at),
            )
            documents_by_folder.setdefault(folder_name, []).append(document)
            chunk_counts[folder_name] = chunk_counts.get(folder_name, 0) + document.chunk_count

        folders = [
            FolderSummary(
                name=row.name,
                origin=row.origin,
                updated_at=self._serialize_timestamp(row.updated_at),
                document_count=len(documents_by_folder.get(row.name, [])),
                chunk_count=chunk_counts.get(row.name, 0),
                documents=documents_by_folder.get(row.name, []),
            )
            for row in folder_rows
        ]

        return FolderListResponse(folders=folders)

    def sync_example_files(self) -> FolderSyncResponse:
        ingest_files: list[IngestFile] = []

        for path in sorted(self._examples_root.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith("."):
                continue

            extension = path.suffix.lower()
            if extension not in SUPPORTED_EXTENSIONS:
                continue

            ingest_files.append(
                IngestFile(
                    relative_path=str(path.relative_to(self._examples_root)),
                    filename=path.name,
                    content_type=SUPPORTED_EXTENSIONS[extension],
                    data=path.read_bytes(),
                )
            )

        return self._sync_folder_batch(
            folder_name="Examples",
            origin="api_examples",
            files=ingest_files,
            prune_missing_documents=True,
        )

    def sync_browser_uploads(self, files: list[IngestFile]) -> FolderSyncResponse:
        grouped: dict[str, list[IngestFile]] = {}

        for file in files:
            parts = Path(file.relative_path).parts
            if not parts:
                continue

            folder_name = parts[0] or "Uploads"
            relative_parts = parts[1:] if len(parts) > 1 else (file.filename,)
            relative_path = str(Path(*relative_parts))

            grouped.setdefault(folder_name, []).append(
                IngestFile(
                    relative_path=relative_path,
                    filename=Path(relative_path).name,
                    content_type=file.content_type,
                    data=file.data,
                )
            )

        processed_files: list[ProcessedFileResult] = []
        for folder_name, folder_files in grouped.items():
            result = self._sync_folder_batch(
                folder_name=folder_name,
                origin="browser_upload",
                files=folder_files,
                prune_missing_documents=False,
            )
            processed_files.extend(result.processed_files)

        folders = self.list_folders()
        return FolderSyncResponse(folders=folders.folders, processed_files=processed_files)

    def search_chunks(
        self,
        *,
        folder_names: list[str] | None = None,
    ) -> list[ChunkRecord]:
        rows = self._documents.search_chunks(
            embedding_model=self._ollama_client.embedding_model,
            folder_names=folder_names,
        )

        return [
            ChunkRecord(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                folder_name=row.folder_name,
                document_name=row.document_name,
                relative_path=row.relative_path,
                text=row.text,
                chunk_index=row.chunk_index,
                embedding=json.loads(row.embedding_json) if row.embedding_json else None,
                embedding_model=row.embedding_model,
            )
            for row in rows
        ]

    def remove_document(self, document_id: str) -> FolderListResponse:
        row = self._documents.get_document_location(document_id)
        if row is None:
            return self.list_folders()

        self._delete_document_record(
            document_id=document_id,
            storage_path=row.storage_path,
        )
        self._prune_empty_folder(row.folder_id)
        return self.list_folders()

    def clear_folder(self, folder_name: str) -> FolderListResponse:
        folder_id = self._documents.get_folder_id(folder_name)
        if folder_id is None:
            return self.list_folders()

        for document in self._documents.list_folder_documents(folder_id):
            self._delete_document_record(
                document_id=document.document_id,
                storage_path=document.storage_path,
            )

        self._documents.delete_folder(folder_id)
        return self.list_folders()

    def get_document_file(self, document_id: str) -> StoredDocumentFile | None:
        row = self._documents.get_document_file(document_id)
        if row is None:
            return None

        storage_path = Path(row.storage_path).resolve()
        storage_root = self._storage_root.resolve()

        try:
            storage_path.relative_to(storage_root)
        except ValueError:
            return None

        if not storage_path.is_file():
            return None

        return StoredDocumentFile(
            document_id=row.document_id,
            filename=row.filename,
            media_type=row.media_type,
            storage_path=storage_path,
        )

    def _sync_folder_batch(
        self,
        *,
        folder_name: str,
        origin: str,
        files: list[IngestFile],
        prune_missing_documents: bool,
    ) -> FolderSyncResponse:
        folder_id = self._documents.upsert_folder(folder_name, origin)
        processed_files: list[ProcessedFileResult] = []
        active_relative_paths: list[str] = []

        for file in files:
            extension = Path(file.filename).suffix.lower()
            if extension not in SUPPORTED_EXTENSIONS:
                processed_files.append(
                    ProcessedFileResult(
                        folder_name=folder_name,
                        relative_path=file.relative_path,
                        filename=file.filename,
                        status="skipped",
                        reason="Unsupported file type.",
                    )
                )
                continue

            try:
                extracted_text = self._extract_text(file)
            except ValueError as error:
                processed_files.append(
                    ProcessedFileResult(
                        folder_name=folder_name,
                        relative_path=file.relative_path,
                        filename=file.filename,
                        status="skipped",
                        reason=str(error),
                    )
                )
                continue

            chunks = chunk_text(extracted_text)
            if not chunks:
                processed_files.append(
                    ProcessedFileResult(
                        folder_name=folder_name,
                        relative_path=file.relative_path,
                        filename=file.filename,
                        status="skipped",
                        reason="No machine-readable text could be extracted.",
                    )
                )
                continue

            active_relative_paths.append(file.relative_path)
            document_id = self._upsert_document(
                folder_id=folder_id,
                folder_name=folder_name,
                file=file,
                extracted_text=extracted_text,
                chunks=chunks,
            )
            processed_files.append(
                ProcessedFileResult(
                    folder_name=folder_name,
                    relative_path=file.relative_path,
                    filename=file.filename,
                    status="ingested",
                    document_id=document_id,
                    char_count=len(extracted_text),
                    chunk_count=len(chunks),
                )
            )

        if prune_missing_documents:
            self._delete_stale_documents(
                folder_id=folder_id,
                active_relative_paths=active_relative_paths,
            )
        self._documents.touch_folder(folder_id)
        folders = self.list_folders()
        return FolderSyncResponse(folders=folders.folders, processed_files=processed_files)

    def _upsert_document(
        self,
        *,
        folder_id: str,
        folder_name: str,
        file: IngestFile,
        extracted_text: str,
        chunks: list[str],
    ) -> str:
        existing_document_id = self._documents.get_document_id(folder_id, file.relative_path)
        document_id = existing_document_id or str(uuid4())

        storage_path = self._write_file_to_storage(
            folder_name=folder_name,
            document_id=document_id,
            filename=file.filename,
            data=file.data,
        )

        media_type = file.content_type or SUPPORTED_EXTENSIONS.get(Path(file.filename).suffix.lower(), "application/octet-stream")
        content_hash = sha256(file.data).hexdigest()
        document_id = self._documents.upsert_document(
            folder_id=folder_id,
            filename=file.filename,
            relative_path=file.relative_path,
            storage_path=storage_path,
            media_type=media_type,
            sha256=content_hash,
            extracted_text=extracted_text,
            char_count=len(extracted_text),
            chunk_count=len(chunks),
        )

        chunk_records = self._documents.replace_document_chunks(document_id, chunks)

        self._store_chunk_embeddings(chunk_records)

        return document_id

    def _delete_stale_documents(self, *, folder_id: str, active_relative_paths: list[str]) -> None:
        rows = self._documents.list_stored_folder_documents(folder_id)
        active_set = set(active_relative_paths)
        for document in rows:
            if document.relative_path in active_set:
                continue

            self._delete_document_record(
                document_id=document.document_id,
                storage_path=document.storage_path,
            )

    def _extract_text(self, file: IngestFile) -> str:
        extension = Path(file.filename).suffix.lower()
        if extension == ".pdf":
            reader = PdfReader(BytesIO(file.data))
            text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)
        elif extension == ".json":
            parsed = json.loads(file.data.decode("utf-8"))
            text = json.dumps(parsed, indent=2, ensure_ascii=True)
        else:
            text = file.data.decode("utf-8", errors="ignore")

        normalized = normalize_text(text)
        if not normalized:
            raise ValueError("No machine-readable text could be extracted.")
        return normalized

    def _write_file_to_storage(
        self,
        *,
        folder_name: str,
        document_id: str,
        filename: str,
        data: bytes,
    ) -> str:
        safe_folder = self._slugify(folder_name)
        safe_filename = self._slugify(Path(filename).stem)
        extension = Path(filename).suffix.lower()
        target_dir = self._storage_root / safe_folder / document_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{safe_filename}{extension}"
        target_path.write_bytes(data)
        return str(target_path)

    def _store_chunk_embeddings(self, chunk_records: list[tuple[str, str]]) -> None:
        if not chunk_records:
            return

        try:
            embeddings = self._ollama_client.embed_texts(
                [chunk_text for _, chunk_text in chunk_records]
            )
        except OllamaServiceError:
            return

        for (chunk_id, _), embedding in zip(chunk_records, embeddings, strict=False):
            self._documents.store_chunk_embedding(
                chunk_id=chunk_id,
                embedding_model=self._ollama_client.embedding_model,
                embedding=embedding,
            )

    def _delete_document_record(self, *, document_id: str, storage_path: str) -> None:
        self._documents.delete_document_tree(document_id)

        stored_file = Path(storage_path)
        if stored_file.exists():
            stored_file.unlink()

        parent_dir = stored_file.parent
        if parent_dir.exists():
            try:
                parent_dir.rmdir()
            except OSError:
                pass

    def _prune_empty_folder(self, folder_id: str) -> None:
        if self._documents.count_documents(folder_id) == 0:
            self._documents.delete_folder(folder_id)

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
        return normalized or "document"

    def _serialize_timestamp(self, raw_value: object) -> str:
        if isinstance(raw_value, datetime):
            return raw_value.isoformat()
        return str(raw_value)
