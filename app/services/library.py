from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import re
from uuid import uuid4

from pypdf import PdfReader

from app.db.connection import DatabaseManager
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


class LibraryService:
    def __init__(
        self,
        database: DatabaseManager,
        ollama_client: OllamaClient,
        *,
        storage_root: str,
        examples_root: str,
    ) -> None:
        self._database = database
        self._ollama_client = ollama_client
        self._storage_root = Path(storage_root)
        self._examples_root = Path(examples_root)

    def list_folders(self) -> FolderListResponse:
        folder_rows = self._database.fetchall(
            """
            SELECT
                id,
                name,
                origin,
                updated_at
            FROM folders
            ORDER BY updated_at DESC, name ASC
            """
        )

        document_rows = self._database.fetchall(
            """
            SELECT
                documents.id,
                folders.name,
                documents.filename,
                documents.relative_path,
                documents.media_type,
                documents.char_count,
                documents.chunk_count,
                documents.updated_at
            FROM documents
            INNER JOIN folders ON folders.id = documents.folder_id
            ORDER BY folders.name ASC, documents.relative_path ASC
            """
        )

        documents_by_folder: dict[str, list[DocumentSummary]] = {}
        chunk_counts: dict[str, int] = {}

        for row in document_rows:
            folder_name = str(row[1])
            document = DocumentSummary(
                id=str(row[0]),
                filename=str(row[2]),
                relative_path=str(row[3]),
                media_type=str(row[4]),
                char_count=int(row[5]),
                chunk_count=int(row[6]),
                updated_at=self._serialize_timestamp(row[7]),
            )
            documents_by_folder.setdefault(folder_name, []).append(document)
            chunk_counts[folder_name] = chunk_counts.get(folder_name, 0) + document.chunk_count

        folders = [
            FolderSummary(
                name=str(row[1]),
                origin=str(row[2]),
                updated_at=self._serialize_timestamp(row[3]),
                document_count=len(documents_by_folder.get(str(row[1]), [])),
                chunk_count=chunk_counts.get(str(row[1]), 0),
                documents=documents_by_folder.get(str(row[1]), []),
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
            )
            processed_files.extend(result.processed_files)

        folders = self.list_folders()
        return FolderSyncResponse(folders=folders.folders, processed_files=processed_files)

    def search_chunks(
        self,
        *,
        folder_names: list[str] | None = None,
    ) -> list[ChunkRecord]:
        params: list[object] = [self._ollama_client.embedding_model]

        if folder_names:
            placeholders = ",".join(["?"] * len(folder_names))
            params.extend(folder_names)
            rows = self._database.fetchall(
                f"""
                SELECT
                    chunks.id,
                    documents.id,
                    folders.name,
                    documents.filename,
                    documents.relative_path,
                    chunks.text,
                    chunks.chunk_index,
                    chunk_embeddings.embedding_json,
                    chunk_embeddings.embedding_model
                FROM chunks
                INNER JOIN documents ON documents.id = chunks.document_id
                INNER JOIN folders ON folders.id = documents.folder_id
                LEFT JOIN chunk_embeddings
                    ON chunk_embeddings.chunk_id = chunks.id
                    AND chunk_embeddings.embedding_model = ?
                WHERE folders.name IN ({placeholders})
                ORDER BY folders.name ASC, documents.relative_path ASC, chunks.chunk_index ASC
                """,
                params,
            )
        else:
            rows = self._database.fetchall(
                """
                SELECT
                    chunks.id,
                    documents.id,
                    folders.name,
                    documents.filename,
                    documents.relative_path,
                    chunks.text,
                    chunks.chunk_index,
                    chunk_embeddings.embedding_json,
                    chunk_embeddings.embedding_model
                FROM chunks
                INNER JOIN documents ON documents.id = chunks.document_id
                INNER JOIN folders ON folders.id = documents.folder_id
                LEFT JOIN chunk_embeddings
                    ON chunk_embeddings.chunk_id = chunks.id
                    AND chunk_embeddings.embedding_model = ?
                ORDER BY folders.name ASC, documents.relative_path ASC, chunks.chunk_index ASC
                """,
                params,
            )

        records = [
            ChunkRecord(
                chunk_id=str(row[0]),
                document_id=str(row[1]),
                folder_name=str(row[2]),
                document_name=str(row[3]),
                relative_path=str(row[4]),
                text=str(row[5]),
                chunk_index=int(row[6]),
                embedding=json.loads(str(row[7])) if row[7] else None,
                embedding_model=str(row[8]) if row[8] else None,
            )
            for row in rows
        ]

        return self._backfill_missing_embeddings(records)

    def _sync_folder_batch(
        self,
        *,
        folder_name: str,
        origin: str,
        files: list[IngestFile],
    ) -> FolderSyncResponse:
        folder_id = self._upsert_folder(folder_name, origin)
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

        self._delete_stale_documents(folder_id=folder_id, active_relative_paths=active_relative_paths)
        self._database.execute(
            "UPDATE folders SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [folder_id],
        )
        folders = self.list_folders()
        return FolderSyncResponse(folders=folders.folders, processed_files=processed_files)

    def _upsert_folder(self, folder_name: str, origin: str) -> str:
        existing = self._database.fetchone(
            "SELECT id FROM folders WHERE name = ?",
            [folder_name],
        )
        if existing:
            folder_id = str(existing[0])
            self._database.execute(
                """
                UPDATE folders
                SET origin = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                [origin, folder_id],
            )
            return folder_id

        folder_id = str(uuid4())
        self._database.execute(
            """
            INSERT INTO folders (id, name, origin)
            VALUES (?, ?, ?)
            """,
            [folder_id, folder_name, origin],
        )
        return folder_id

    def _upsert_document(
        self,
        *,
        folder_id: str,
        folder_name: str,
        file: IngestFile,
        extracted_text: str,
        chunks: list[str],
    ) -> str:
        existing = self._database.fetchone(
            """
            SELECT id
            FROM documents
            WHERE folder_id = ? AND relative_path = ?
            """,
            [folder_id, file.relative_path],
        )
        document_id = str(existing[0]) if existing else str(uuid4())

        storage_path = self._write_file_to_storage(
            folder_name=folder_name,
            document_id=document_id,
            filename=file.filename,
            data=file.data,
        )

        media_type = file.content_type or SUPPORTED_EXTENSIONS.get(Path(file.filename).suffix.lower(), "application/octet-stream")
        content_hash = sha256(file.data).hexdigest()

        if existing:
            self._database.execute(
                """
                DELETE FROM chunk_embeddings
                WHERE chunk_id IN (
                    SELECT id
                    FROM chunks
                    WHERE document_id = ?
                )
                """,
                [document_id],
            )
            self._database.execute(
                """
                UPDATE documents
                SET
                    filename = ?,
                    relative_path = ?,
                    storage_path = ?,
                    media_type = ?,
                    sha256 = ?,
                    extracted_text = ?,
                    char_count = ?,
                    chunk_count = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                [
                    file.filename,
                    file.relative_path,
                    storage_path,
                    media_type,
                    content_hash,
                    extracted_text,
                    len(extracted_text),
                    len(chunks),
                    document_id,
                ],
            )
        else:
            self._database.execute(
                """
                INSERT INTO documents (
                    id,
                    folder_id,
                    filename,
                    relative_path,
                    storage_path,
                    media_type,
                    sha256,
                    extracted_text,
                    char_count,
                    chunk_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    document_id,
                    folder_id,
                    file.filename,
                    file.relative_path,
                    storage_path,
                    media_type,
                    content_hash,
                    extracted_text,
                    len(extracted_text),
                    len(chunks),
                ],
            )

        self._database.execute("DELETE FROM chunks WHERE document_id = ?", [document_id])
        chunk_records: list[tuple[str, str]] = []
        for index, chunk in enumerate(chunks):
            chunk_id = str(uuid4())
            self._database.execute(
                """
                INSERT INTO chunks (id, document_id, chunk_index, text, token_estimate)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    chunk_id,
                    document_id,
                    index,
                    chunk,
                    max(1, len(chunk.split())),
                ],
            )
            chunk_records.append((chunk_id, chunk))

        self._store_chunk_embeddings(chunk_records)

        return document_id

    def _delete_stale_documents(self, *, folder_id: str, active_relative_paths: list[str]) -> None:
        rows = self._database.fetchall(
            """
            SELECT id, relative_path, storage_path
            FROM documents
            WHERE folder_id = ?
            """,
            [folder_id],
        )

        active_set = set(active_relative_paths)
        for document_id, relative_path, storage_path in rows:
            if str(relative_path) in active_set:
                continue

            self._database.execute(
                """
                DELETE FROM chunk_embeddings
                WHERE chunk_id IN (
                    SELECT id
                    FROM chunks
                    WHERE document_id = ?
                )
                """,
                [str(document_id)],
            )
            self._database.execute("DELETE FROM chunks WHERE document_id = ?", [str(document_id)])
            self._database.execute("DELETE FROM documents WHERE id = ?", [str(document_id)])
            stored_file = Path(str(storage_path))
            if stored_file.exists():
                stored_file.unlink()

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
            self._database.execute(
                """
                INSERT OR REPLACE INTO chunk_embeddings (
                    chunk_id,
                    embedding_model,
                    embedding_dimension,
                    embedding_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [
                    chunk_id,
                    self._ollama_client.embedding_model,
                    len(embedding),
                    json.dumps(embedding),
                ],
            )

    def _backfill_missing_embeddings(self, records: list[ChunkRecord]) -> list[ChunkRecord]:
        missing_records = [record for record in records if record.embedding is None]
        if not missing_records:
            return records

        try:
            embeddings = self._ollama_client.embed_texts(
                [record.text for record in missing_records]
            )
        except OllamaServiceError:
            return records

        embeddings_by_chunk_id: dict[str, list[float]] = {}
        for record, embedding in zip(missing_records, embeddings, strict=False):
            embeddings_by_chunk_id[record.chunk_id] = embedding
            self._database.execute(
                """
                INSERT OR REPLACE INTO chunk_embeddings (
                    chunk_id,
                    embedding_model,
                    embedding_dimension,
                    embedding_json,
                    updated_at
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                [
                    record.chunk_id,
                    self._ollama_client.embedding_model,
                    len(embedding),
                    json.dumps(embedding),
                ],
            )

        return [
            replace(
                record,
                embedding=embeddings_by_chunk_id.get(record.chunk_id, record.embedding),
                embedding_model=(
                    self._ollama_client.embedding_model
                    if record.chunk_id in embeddings_by_chunk_id
                    else record.embedding_model
                ),
            )
            for record in records
        ]

    def _slugify(self, value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
        return normalized or "document"

    def _serialize_timestamp(self, raw_value: object) -> str:
        if isinstance(raw_value, datetime):
            return raw_value.isoformat()
        return str(raw_value)
