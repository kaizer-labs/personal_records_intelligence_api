from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from app.db.connection import DatabaseManager


@dataclass(frozen=True)
class ConversationListRecord:
    conversation_id: str
    title: str
    folder_names_json: str
    updated_at: object
    message_count: int
    preview: str | None


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    title: str
    folder_names_json: str


@dataclass(frozen=True)
class MessageRecord:
    message_id: str
    role: str
    content: str
    meta: str | None
    sources_json: str
    created_at: object


class ConversationRepository:
    def __init__(self, database: DatabaseManager) -> None:
        self._database = database

    def list_conversations(self) -> list[ConversationListRecord]:
        rows = self._database.fetchall(
            """
            SELECT
                conversations.id,
                conversations.title,
                conversations.folder_names_json,
                conversations.updated_at,
                COALESCE(message_counts.message_count, 0) AS message_count,
                latest_messages.content
            FROM chat_conversations AS conversations
            LEFT JOIN (
                SELECT conversation_id, COUNT(*) AS message_count
                FROM chat_messages
                GROUP BY conversation_id
            ) AS message_counts
                ON message_counts.conversation_id = conversations.id
            LEFT JOIN (
                SELECT ranked.conversation_id, ranked.content
                FROM (
                    SELECT
                        conversation_id,
                        content,
                        ROW_NUMBER() OVER (
                            PARTITION BY conversation_id
                            ORDER BY sort_index DESC
                        ) AS row_number
                    FROM chat_messages
                ) AS ranked
                WHERE ranked.row_number = 1
            ) AS latest_messages
                ON latest_messages.conversation_id = conversations.id
            ORDER BY conversations.updated_at DESC, conversations.created_at DESC
            """
        )

        return [
            ConversationListRecord(
                conversation_id=str(row[0]),
                title=str(row[1]),
                folder_names_json=str(row[2]),
                updated_at=row[3],
                message_count=int(row[4]),
                preview=str(row[5]) if row[5] else None,
            )
            for row in rows
        ]

    def get_conversation(self, conversation_id: str) -> ConversationListRecord | None:
        row = self._database.fetchone(
            """
            SELECT
                conversations.id,
                conversations.title,
                conversations.folder_names_json,
                conversations.updated_at,
                COALESCE(message_counts.message_count, 0) AS message_count,
                latest_messages.content
            FROM chat_conversations AS conversations
            LEFT JOIN (
                SELECT conversation_id, COUNT(*) AS message_count
                FROM chat_messages
                GROUP BY conversation_id
            ) AS message_counts
                ON message_counts.conversation_id = conversations.id
            LEFT JOIN (
                SELECT ranked.conversation_id, ranked.content
                FROM (
                    SELECT
                        conversation_id,
                        content,
                        ROW_NUMBER() OVER (
                            PARTITION BY conversation_id
                            ORDER BY sort_index DESC
                        ) AS row_number
                    FROM chat_messages
                ) AS ranked
                WHERE ranked.row_number = 1
            ) AS latest_messages
                ON latest_messages.conversation_id = conversations.id
            WHERE conversations.id = ?
            """,
            [conversation_id],
        )
        if row is None:
            return None

        return ConversationListRecord(
            conversation_id=str(row[0]),
            title=str(row[1]),
            folder_names_json=str(row[2]),
            updated_at=row[3],
            message_count=int(row[4]),
            preview=str(row[5]) if row[5] else None,
        )

    def list_messages(self, conversation_id: str) -> list[MessageRecord]:
        rows = self._database.fetchall(
            """
            SELECT
                id,
                role,
                content,
                meta,
                sources_json,
                created_at
            FROM chat_messages
            WHERE conversation_id = ?
            ORDER BY sort_index ASC
            """,
            [conversation_id],
        )

        return [
            MessageRecord(
                message_id=str(row[0]),
                role=str(row[1]),
                content=str(row[2]),
                meta=str(row[3]) if row[3] else None,
                sources_json=str(row[4] or "[]"),
                created_at=row[5],
            )
            for row in rows
        ]

    def delete_conversation(self, conversation_id: str) -> None:
        self._database.execute(
            "DELETE FROM chat_messages WHERE conversation_id = ?",
            [conversation_id],
        )
        self._database.execute(
            "DELETE FROM chat_conversations WHERE id = ?",
            [conversation_id],
        )

    def get_conversation_record(self, conversation_id: str) -> ConversationRecord | None:
        row = self._database.fetchone(
            """
            SELECT id, title, folder_names_json
            FROM chat_conversations
            WHERE id = ?
            """,
            [conversation_id],
        )
        if row is None:
            return None

        return ConversationRecord(
            conversation_id=str(row[0]),
            title=str(row[1]),
            folder_names_json=str(row[2]),
        )

    def update_conversation_folders(
        self,
        conversation_id: str,
        folder_names_json: str,
    ) -> None:
        self._database.execute(
            """
            UPDATE chat_conversations
            SET folder_names_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [folder_names_json, conversation_id],
        )

    def create_conversation(
        self,
        *,
        title: str,
        folder_names_json: str,
    ) -> ConversationRecord:
        conversation_id = str(uuid4())
        self._database.execute(
            """
            INSERT INTO chat_conversations (id, title, folder_names_json)
            VALUES (?, ?, ?)
            """,
            [conversation_id, title, folder_names_json],
        )
        return ConversationRecord(
            conversation_id=conversation_id,
            title=title,
            folder_names_json=folder_names_json,
        )

    def append_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        meta: str | None,
        sources_json: str,
    ) -> None:
        next_sort_index_row = self._database.fetchone(
            """
            SELECT COALESCE(MAX(sort_index), -1) + 1
            FROM chat_messages
            WHERE conversation_id = ?
            """,
            [conversation_id],
        )
        next_sort_index = int(next_sort_index_row[0]) if next_sort_index_row else 0

        self._database.execute(
            """
            INSERT INTO chat_messages (
                id,
                conversation_id,
                role,
                content,
                meta,
                sources_json,
                sort_index
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                str(uuid4()),
                conversation_id,
                role,
                content,
                meta,
                sources_json,
                next_sort_index,
            ],
        )
        self._database.execute(
            """
            UPDATE chat_conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [conversation_id],
        )
