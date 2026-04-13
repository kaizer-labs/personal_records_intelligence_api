from __future__ import annotations

from dataclasses import dataclass
import json
from uuid import uuid4

from app.db.connection import DatabaseManager


@dataclass(frozen=True)
class FolderRecord:
    folder_id: str
    name: str
    origin: str
    updated_at: object


@dataclass(frozen=True)
class DocumentSummaryRecord:
    document_id: str
    folder_name: str
    filename: str
    relative_path: str
    media_type: str
    char_count: int
    chunk_count: int
    updated_at: object


@dataclass(frozen=True)
class ChunkSearchRecord:
    chunk_id: str
    document_id: str
    folder_name: str
    document_name: str
    relative_path: str
    text: str
    chunk_index: int
    embedding_json: str | None
    embedding_model: str | None


@dataclass(frozen=True)
class DocumentLocationRecord:
    document_id: str
    folder_id: str
    storage_path: str


@dataclass(frozen=True)
class DocumentFileRecord:
    document_id: str
    filename: str
    media_type: str
    storage_path: str


@dataclass(frozen=True)
class FolderDocumentRecord:
    document_id: str
    storage_path: str


@dataclass(frozen=True)
class StoredFolderDocumentRecord:
    document_id: str
    relative_path: str
    storage_path: str


class DocumentRepository:
    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    def list_folders(self) -> list[FolderRecord]:
        rows = self._database.fetchall(
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

        return [
            FolderRecord(
                folder_id=str(row[0]),
                name=str(row[1]),
                origin=str(row[2]),
                updated_at=row[3],
            )
            for row in rows
        ]

    def list_documents(self) -> list[DocumentSummaryRecord]:
        rows = self._database.fetchall(
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

        return [
            DocumentSummaryRecord(
                document_id=str(row[0]),
                folder_name=str(row[1]),
                filename=str(row[2]),
                relative_path=str(row[3]),
                media_type=str(row[4]),
                char_count=int(row[5]),
                chunk_count=int(row[6]),
                updated_at=row[7],
            )
            for row in rows
        ]

    def search_chunks(
        self,
        *,
        embedding_model: str,
        folder_names: list[str] | None = None,
    ) -> list[ChunkSearchRecord]:
        params: list[object] = [embedding_model]

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

        return [
            ChunkSearchRecord(
                chunk_id=str(row[0]),
                document_id=str(row[1]),
                folder_name=str(row[2]),
                document_name=str(row[3]),
                relative_path=str(row[4]),
                text=str(row[5]),
                chunk_index=int(row[6]),
                embedding_json=str(row[7]) if row[7] else None,
                embedding_model=str(row[8]) if row[8] else None,
            )
            for row in rows
        ]

    def get_document_location(self, document_id: str) -> DocumentLocationRecord | None:
        row = self._database.fetchone(
            """
            SELECT
                documents.id,
                documents.folder_id,
                documents.storage_path
            FROM documents
            WHERE documents.id = ?
            """,
            [document_id],
        )
        if row is None:
            return None

        return DocumentLocationRecord(
            document_id=str(row[0]),
            folder_id=str(row[1]),
            storage_path=str(row[2]),
        )

    def get_folder_id(self, folder_name: str) -> str | None:
        row = self._database.fetchone(
            """
            SELECT id
            FROM folders
            WHERE name = ?
            """,
            [folder_name],
        )
        return str(row[0]) if row else None

    def list_folder_documents(self, folder_id: str) -> list[FolderDocumentRecord]:
        rows = self._database.fetchall(
            """
            SELECT id, storage_path
            FROM documents
            WHERE folder_id = ?
            """,
            [folder_id],
        )

        return [
            FolderDocumentRecord(
                document_id=str(row[0]),
                storage_path=str(row[1]),
            )
            for row in rows
        ]

    def delete_folder(self, folder_id: str) -> None:
        self._database.execute("DELETE FROM folders WHERE id = ?", [folder_id])

    def get_document_file(self, document_id: str) -> DocumentFileRecord | None:
        row = self._database.fetchone(
            """
            SELECT
                id,
                filename,
                media_type,
                storage_path
            FROM documents
            WHERE id = ?
            """,
            [document_id],
        )
        if row is None:
            return None

        return DocumentFileRecord(
            document_id=str(row[0]),
            filename=str(row[1]),
            media_type=str(row[2]),
            storage_path=str(row[3]),
        )

    def touch_folder(self, folder_id: str) -> None:
        self._database.execute(
            "UPDATE folders SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            [folder_id],
        )

    def upsert_folder(self, folder_name: str, origin: str) -> str:
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

    def get_document_id(self, folder_id: str, relative_path: str) -> str | None:
        row = self._database.fetchone(
            """
            SELECT id
            FROM documents
            WHERE folder_id = ? AND relative_path = ?
            """,
            [folder_id, relative_path],
        )
        return str(row[0]) if row else None

    def upsert_document(
        self,
        *,
        folder_id: str,
        filename: str,
        relative_path: str,
        storage_path: str,
        media_type: str,
        sha256: str,
        extracted_text: str,
        char_count: int,
        chunk_count: int,
    ) -> str:
        existing = self._database.fetchone(
            """
            SELECT id
            FROM documents
            WHERE folder_id = ? AND relative_path = ?
            """,
            [folder_id, relative_path],
        )
        document_id = str(existing[0]) if existing else str(uuid4())

        if existing:
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
                    filename,
                    relative_path,
                    storage_path,
                    media_type,
                    sha256,
                    extracted_text,
                    char_count,
                    chunk_count,
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
                    filename,
                    relative_path,
                    storage_path,
                    media_type,
                    sha256,
                    extracted_text,
                    char_count,
                    chunk_count,
                ],
            )

        return document_id

    def replace_document_chunks(
        self,
        document_id: str,
        chunks: list[str],
    ) -> list[tuple[str, str]]:
        self._delete_chunk_embeddings_for_document(document_id)
        self._delete_chunks_for_document(document_id)

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

        return chunk_records

    def list_stored_folder_documents(self, folder_id: str) -> list[StoredFolderDocumentRecord]:
        rows = self._database.fetchall(
            """
            SELECT id, relative_path, storage_path
            FROM documents
            WHERE folder_id = ?
            """,
            [folder_id],
        )

        return [
            StoredFolderDocumentRecord(
                document_id=str(row[0]),
                relative_path=str(row[1]),
                storage_path=str(row[2]),
            )
            for row in rows
        ]

    def store_chunk_embedding(
        self,
        *,
        chunk_id: str,
        embedding_model: str,
        embedding: list[float],
    ) -> None:
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
                embedding_model,
                len(embedding),
                json.dumps(embedding),
            ],
        )

    def delete_document_tree(self, document_id: str) -> None:
        self._delete_chunk_embeddings_for_document(document_id)
        self._delete_chunks_for_document(document_id)
        self._database.execute("DELETE FROM documents WHERE id = ?", [document_id])

    def count_documents(self, folder_id: str) -> int:
        document_count = self._database.fetchone(
            "SELECT COUNT(*) FROM documents WHERE folder_id = ?",
            [folder_id],
        )
        return int(document_count[0]) if document_count else 0

    def _delete_chunk_embeddings_for_document(self, document_id: str) -> None:
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

    def _delete_chunks_for_document(self, document_id: str) -> None:
        self._database.execute("DELETE FROM chunks WHERE document_id = ?", [document_id])
