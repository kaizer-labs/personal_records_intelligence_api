from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Iterator
from uuid import uuid4

from app.db.connection import DatabaseManager
from app.schemas.chat import (
    ChatConversationDetailResponse,
    ChatConversationListResponse,
    ChatConversationSummary,
    ChatMessage,
    ChatResponse,
    ChatSource,
)
from app.services.library import ChunkRecord, LibraryService
from app.services.ollama import OllamaClient, OllamaServiceError
from app.services.text_processing import (
    boilerplate_penalty,
    build_excerpt,
    cosine_similarity,
    count_currency_values,
    count_date_values,
    detect_query_intents,
    has_contextual_follow_up_reference,
    is_explicitly_off_topic,
    looks_like_document_request,
    score_text,
)


@dataclass
class RankedChunk:
    chunk_id: str
    document_id: str
    folder_name: str
    document_name: str
    relative_path: str
    text: str
    score: float
    lexical_score: float
    semantic_score: float


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    title: str
    folder_names: list[str]


@dataclass(frozen=True)
class PreparedChatOutcome:
    conversation: ConversationRecord
    folder_names: list[str]
    user_meta: str
    system_prompt: str | None = None
    user_prompt: str | None = None
    query_intents: set[str] = field(default_factory=set)
    sources: list[ChatSource] = field(default_factory=list)
    immediate_response: ChatResponse | None = None


class ChatService:
    def __init__(
        self,
        database: DatabaseManager,
        library_service: LibraryService,
        ollama_client: OllamaClient,
    ) -> None:
        self._database = database
        self._library_service = library_service
        self._ollama_client = ollama_client

    def list_conversations(self) -> ChatConversationListResponse:
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

        return ChatConversationListResponse(
            conversations=[
                ChatConversationSummary(
                    id=str(row[0]),
                    title=str(row[1]),
                    folder_names=self._parse_folder_names(row[2]),
                    updated_at=self._serialize_timestamp(row[3]),
                    message_count=int(row[4]),
                    preview=str(row[5]) if row[5] else None,
                )
                for row in rows
            ]
        )

    def get_conversation(
        self,
        conversation_id: str,
    ) -> ChatConversationDetailResponse | None:
        conversation_row = self._database.fetchone(
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
        if conversation_row is None:
            return None

        message_rows = self._database.fetchall(
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

        conversation = ChatConversationSummary(
            id=str(conversation_row[0]),
            title=str(conversation_row[1]),
            folder_names=self._parse_folder_names(conversation_row[2]),
            updated_at=self._serialize_timestamp(conversation_row[3]),
            message_count=int(conversation_row[4]),
            preview=str(conversation_row[5]) if conversation_row[5] else None,
        )
        messages = [
            ChatMessage(
                id=str(row[0]),
                role=str(row[1]),
                content=str(row[2]),
                meta=str(row[3]) if row[3] else None,
                sources=[
                    ChatSource(**source_payload)
                    for source_payload in json.loads(str(row[4]) or "[]")
                ],
                created_at=self._serialize_timestamp(row[5]),
            )
            for row in message_rows
        ]
        return ChatConversationDetailResponse(conversation=conversation, messages=messages)

    def delete_conversation(self, conversation_id: str) -> ChatConversationListResponse:
        self._database.execute(
            "DELETE FROM chat_messages WHERE conversation_id = ?",
            [conversation_id],
        )
        self._database.execute(
            "DELETE FROM chat_conversations WHERE id = ?",
            [conversation_id],
        )
        return self.list_conversations()

    def answer_question(
        self,
        *,
        question: str,
        folder_names: list[str],
        conversation_id: str | None = None,
    ) -> ChatResponse:
        prepared = self._prepare_chat_outcome(
            question=question,
            folder_names=folder_names,
            conversation_id=conversation_id,
        )
        self._append_message(
            conversation_id=prepared.conversation.conversation_id,
            role="user",
            content=question,
            meta=prepared.user_meta,
        )
        if prepared.immediate_response is not None:
            self._append_response_message(prepared.immediate_response)
            return prepared.immediate_response

        result = self._ollama_client.chat(
            system_prompt=prepared.system_prompt or "",
            user_prompt=prepared.user_prompt or "",
        )
        response = self._build_chat_response(
            prepared=prepared,
            answer=result.content,
            model=result.model,
        )
        self._append_response_message(response)
        return response

    def stream_answer_question(
        self,
        *,
        question: str,
        folder_names: list[str],
        conversation_id: str | None = None,
    ) -> Iterator[str]:
        prepared = self._prepare_chat_outcome(
            question=question,
            folder_names=folder_names,
            conversation_id=conversation_id,
        )
        self._append_message(
            conversation_id=prepared.conversation.conversation_id,
            role="user",
            content=question,
            meta=prepared.user_meta,
        )

        if prepared.immediate_response is not None:
            self._append_response_message(prepared.immediate_response)
            yield self._serialize_stream_event(
                "start",
                {
                    "conversation_id": prepared.immediate_response.conversation_id,
                    "conversation_title": prepared.immediate_response.conversation_title,
                    "selected_folders": prepared.immediate_response.selected_folders,
                    "sources": self._serialize_sources(prepared.immediate_response.sources),
                    "model": prepared.immediate_response.model,
                },
            )
            yield self._serialize_stream_event(
                "final",
                self._response_payload(prepared.immediate_response),
            )
            return

        yield self._serialize_stream_event(
            "start",
            {
                "conversation_id": prepared.conversation.conversation_id,
                "conversation_title": prepared.conversation.title,
                "selected_folders": prepared.folder_names,
                "sources": self._serialize_sources(prepared.sources),
                "model": self._ollama_client.chat_model,
            },
        )

        response_model = self._ollama_client.chat_model
        answer_parts: list[str] = []

        try:
            for delta in self._ollama_client.chat_stream(
                system_prompt=prepared.system_prompt or "",
                user_prompt=prepared.user_prompt or "",
            ):
                response_model = delta.model or response_model
                if delta.content:
                    answer_parts.append(delta.content)
                    yield self._serialize_stream_event("delta", {"delta": delta.content})
        except OllamaServiceError as error:
            yield self._serialize_stream_event("error", {"detail": str(error)})
            return

        full_answer = "".join(answer_parts).strip()
        if not full_answer:
            yield self._serialize_stream_event(
                "error",
                {"detail": "Ollama returned an empty response."},
            )
            return

        response = self._build_chat_response(
            prepared=prepared,
            answer=full_answer,
            model=response_model,
        )
        self._append_response_message(response)
        yield self._serialize_stream_event("final", self._response_payload(response))

    def _rank_chunks(
        self,
        *,
        question: str,
        chunks: list[ChunkRecord],
    ) -> list[RankedChunk]:
        query_embedding: list[float] | None = None
        try:
            query_embedding = self._ollama_client.embed_text(question)
        except OllamaServiceError:
            query_embedding = None

        ranked = [
            self._build_ranked_chunk(
                question=question,
                chunk=chunk,
                query_embedding=query_embedding,
            )
            for chunk in chunks
        ]

        ranked.sort(key=lambda item: item.score, reverse=True)
        positive_matches = [chunk for chunk in ranked if chunk.score > 0]
        if positive_matches:
            return positive_matches

        return ranked[:4]

    def _select_context_chunks(
        self,
        *,
        question: str,
        ranked_chunks: list[RankedChunk],
        limit: int,
    ) -> list[RankedChunk]:
        if not ranked_chunks:
            return []

        selected: list[RankedChunk] = []
        selected_ids: set[str] = set()
        selected_fingerprints: set[str] = set()
        per_document: dict[str, int] = {}

        for max_per_document in (1, 2, 3):
            for chunk in ranked_chunks:
                if len(selected) >= limit:
                    return selected
                if chunk.chunk_id in selected_ids:
                    continue
                if per_document.get(chunk.document_id, 0) >= max_per_document:
                    continue

                fingerprint = self._fingerprint_chunk_text(chunk.text)
                if fingerprint in selected_fingerprints:
                    continue
                if self._is_low_value_disclaimer(chunk):
                    continue

                selected.append(chunk)
                selected_ids.add(chunk.chunk_id)
                selected_fingerprints.add(fingerprint)
                per_document[chunk.document_id] = per_document.get(chunk.document_id, 0) + 1

        if selected:
            return selected

        return ranked_chunks[:limit]

    def _build_no_records_response(
        self,
        *,
        conversation: ConversationRecord,
        folder_names: list[str],
    ) -> ChatResponse:
        return ChatResponse(
            conversation_id=conversation.conversation_id,
            conversation_title=conversation.title,
            answer=(
                "No relevant records found for that question in the selected folders. "
                "Try asking about details that appear in the documents, such as dates, amounts, people, obligations, or summaries."
            ),
            model=self._ollama_client.chat_model,
            selected_folders=folder_names,
            sources=[],
        )

    def _should_return_no_records(
        self,
        *,
        question: str,
        ranked_chunks: list[RankedChunk],
        prior_messages: list[ChatMessage],
    ) -> bool:
        if not ranked_chunks:
            return True

        has_grounded_history = any(message.sources for message in prior_messages)
        if has_grounded_history and has_contextual_follow_up_reference(question):
            return False

        top_ranked_chunks = ranked_chunks[:5]
        top_lexical = max(chunk.lexical_score for chunk in top_ranked_chunks)
        top_semantic = max(chunk.semantic_score for chunk in top_ranked_chunks)
        top_score = max(chunk.score for chunk in top_ranked_chunks)

        if top_lexical >= 1.0:
            return False

        if looks_like_document_request(question):
            return top_semantic < 0.32 and top_score < 0.9

        return top_semantic < 0.45 and top_score < 1.0

    def _prepare_chat_outcome(
        self,
        *,
        question: str,
        folder_names: list[str],
        conversation_id: str | None,
    ) -> PreparedChatOutcome:
        normalized_folders = self._normalize_folder_names(folder_names)
        conversation = self._load_existing_conversation(
            conversation_id=conversation_id,
            folder_names=normalized_folders,
        )
        prior_messages = (
            self._get_conversation_messages(conversation.conversation_id)
            if conversation is not None
            else []
        )
        user_meta = (
            f"Searching {len(normalized_folders)} folder"
            f"{'' if len(normalized_folders) == 1 else 's'}"
            if normalized_folders
            else "Searching all indexed folders"
        )
        persisted_conversation = conversation or self._create_conversation(
            question=question,
            folder_names=normalized_folders,
        )

        chunks = self._library_service.search_chunks(folder_names=normalized_folders or None)
        if not chunks:
            return PreparedChatOutcome(
                conversation=persisted_conversation,
                folder_names=normalized_folders,
                user_meta=user_meta,
                immediate_response=ChatResponse(
                    conversation_id=persisted_conversation.conversation_id,
                    conversation_title=persisted_conversation.title,
                    answer="I don't have any indexed documents yet. Add a folder or load the example document first.",
                    model=self._ollama_client.chat_model,
                    selected_folders=normalized_folders,
                    sources=[],
                ),
            )

        if is_explicitly_off_topic(question):
            return PreparedChatOutcome(
                conversation=persisted_conversation,
                folder_names=normalized_folders,
                user_meta=user_meta,
                immediate_response=self._build_no_records_response(
                    conversation=persisted_conversation,
                    folder_names=normalized_folders,
                ),
            )

        ranked_chunks = self._rank_chunks(question=question, chunks=chunks)
        if self._should_return_no_records(
            question=question,
            ranked_chunks=ranked_chunks,
            prior_messages=prior_messages,
        ):
            return PreparedChatOutcome(
                conversation=persisted_conversation,
                folder_names=normalized_folders,
                user_meta=user_meta,
                immediate_response=self._build_no_records_response(
                    conversation=persisted_conversation,
                    folder_names=normalized_folders,
                ),
            )

        top_chunks = self._select_context_chunks(
            question=question,
            ranked_chunks=ranked_chunks,
            limit=5,
        )
        if not top_chunks:
            return PreparedChatOutcome(
                conversation=persisted_conversation,
                folder_names=normalized_folders,
                user_meta=user_meta,
                immediate_response=self._build_no_records_response(
                    conversation=persisted_conversation,
                    folder_names=normalized_folders,
                ),
            )

        query_intents = detect_query_intents(question)
        return PreparedChatOutcome(
            conversation=persisted_conversation,
            folder_names=normalized_folders,
            user_meta=user_meta,
            system_prompt=self._build_system_prompt(query_intents),
            user_prompt=self._build_user_prompt(
                question=question,
                query_intents=query_intents,
                prior_messages=prior_messages,
                top_chunks=top_chunks,
            ),
            query_intents=query_intents,
            sources=self._build_sources(question=question, top_chunks=top_chunks),
        )

    def _build_system_prompt(self, query_intents: set[str]) -> str:
        instructions = [
            "Answer using only the provided document context.",
            "If the context does not support the answer, say so clearly.",
            "Lead with the direct answer, then use short Markdown headings and bullets only when they improve clarity.",
            "Treat repeated disclaimer language as secondary when real figures, dates, or obligations are present.",
            "If the documents look like statements or reports, summarize the visible figures and date ranges.",
            "Keep the answer concise, practical, and grounded in the sources.",
            "Do not mention missing earnings, payroll, or income unless the user explicitly asked about them.",
            "Do not add missing-data caveats for fields the user did not request.",
        ]

        if "priorities" in query_intents:
            instructions.extend(
                [
                    "The user is asking what matters most.",
                    "Prioritize by urgency, deadlines, money due, commitments, risks, and next actions.",
                    "When supported, organize the answer into short sections such as Pay attention first, Key dates, Money due, and Commitments.",
                ]
            )
        else:
            instructions.append(
                "For dates, amounts, balances, earnings, or commitments, extract concrete values first."
            )

        if "subscriptions" in query_intents:
            instructions.extend(
                [
                    "The user is asking about subscriptions or recurring plans.",
                    "Only include recurring services, memberships, utilities, insurance plans, or plans with renewal or repeating charges.",
                    "Exclude one-time travel bookings, event agreements, or single purchases unless the document explicitly says they recur.",
                    "If asked whether the user needs it, give a grounded keep, review, or cancel-candidate recommendation based on the document details and say when the recommendation is uncertain because usage context is missing.",
                ]
            )

        return " ".join(instructions)

    def _build_user_prompt(
        self,
        *,
        question: str,
        query_intents: set[str],
        prior_messages: list[ChatMessage],
        top_chunks: list[RankedChunk],
    ) -> str:
        context_blocks: list[str] = []
        for index, chunk in enumerate(top_chunks, start=1):
            context_blocks.append(
                "\n".join(
                    [
                        f"Source {index}",
                        f"Folder: {chunk.folder_name}",
                        f"Document: {chunk.document_name}",
                        f"Path: {chunk.relative_path}",
                        "Excerpt:",
                        build_excerpt(chunk.text, question, max_chars=420),
                    ]
                )
            )

        history_block = self._build_history_block(prior_messages)
        prompt_sections = [f"Question: {question}"]
        if history_block:
            prompt_sections.extend(["Conversation history:", history_block])

        prompt_sections.extend(
            [
                "Context:",
                *context_blocks,
                "Answer using the context above.",
                "If there are multiple matching records or itineraries, summarize them as separate options instead of merging them together.",
                "Mention the document name only when it helps disambiguate.",
            ]
        )

        field_intents = sorted(intent for intent in query_intents if intent != "priorities")
        if field_intents:
            prompt_sections.append(
                "Requested fields: "
                + ", ".join(field_intents)
                + ". If any of these are present, list the concrete values you found."
            )

        if "priorities" in query_intents:
            prompt_sections.append(
                "This is a prioritization request. Focus on what needs attention first, then summarize deadlines, amounts, commitments, and next actions. Ignore unrequested fields, and do not add any 'missing earnings' or 'missing income' caveat."
            )
        if "subscriptions" in query_intents:
            prompt_sections.append(
                "This is a subscription review request. Return one item per recurring subscription or plan with: what it is, current or next cost, renewal timing, and a short keep/review/cancel-candidate note. Exclude one-time travel, catering, or event documents."
            )
        if "earnings" in query_intents:
            prompt_sections.append(
                "If the documents describe investment income, dividends, interest, estimated cash flows, or account balances rather than payroll earnings, say that explicitly and summarize those figures instead of treating them as missing."
            )

        return "\n\n".join(prompt_sections)

    def _build_sources(
        self,
        *,
        question: str,
        top_chunks: list[RankedChunk],
    ) -> list[ChatSource]:
        return [
            ChatSource(
                document_id=chunk.document_id,
                folder_name=chunk.folder_name,
                document_name=chunk.document_name,
                relative_path=chunk.relative_path,
                excerpt=build_excerpt(chunk.text, question),
                score=round(chunk.score, 2),
            )
            for chunk in top_chunks
        ]

    def _build_chat_response(
        self,
        *,
        prepared: PreparedChatOutcome,
        answer: str,
        model: str,
    ) -> ChatResponse:
        return ChatResponse(
            conversation_id=prepared.conversation.conversation_id,
            conversation_title=prepared.conversation.title,
            answer=self._postprocess_answer(answer, prepared.query_intents),
            model=model,
            selected_folders=prepared.folder_names,
            sources=prepared.sources,
        )

    def _build_ranked_chunk(
        self,
        *,
        question: str,
        chunk: ChunkRecord,
        query_embedding: list[float] | None,
    ) -> RankedChunk:
        lexical_score = score_text(
            question,
            f"{chunk.document_name}\n{chunk.relative_path}\n{chunk.text}",
        ) + max(0.0, 1.0 - (chunk.chunk_index * 0.05))
        semantic_score = (
            cosine_similarity(query_embedding, chunk.embedding)
            if query_embedding and chunk.embedding
            else 0.0
        )
        lexical_component = min(lexical_score / 8.0, 1.5)
        semantic_component = max(semantic_score, 0.0) * 4.5

        return RankedChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            folder_name=chunk.folder_name,
            document_name=chunk.document_name,
            relative_path=chunk.relative_path,
            text=chunk.text,
            score=lexical_component + semantic_component,
            lexical_score=lexical_score,
            semantic_score=semantic_score,
        )

    def _fingerprint_chunk_text(self, text: str) -> str:
        collapsed = " ".join(text.lower().split())
        return collapsed[:220]

    def _is_low_value_disclaimer(self, chunk: RankedChunk) -> bool:
        if chunk.score <= 0:
            return False

        if count_currency_values(chunk.text) > 0 or count_date_values(chunk.text) > 0:
            return False

        return boilerplate_penalty(chunk.text) >= 2.5

    def _load_existing_conversation(
        self,
        *,
        folder_names: list[str],
        conversation_id: str | None,
    ) -> ConversationRecord | None:
        if not conversation_id:
            return None

        existing = self._database.fetchone(
            """
            SELECT id, title, folder_names_json
            FROM chat_conversations
            WHERE id = ?
            """,
            [conversation_id],
        )
        if existing is None:
            return None

        stored_folders = self._parse_folder_names(existing[2])
        effective_folders = folder_names or stored_folders
        self._database.execute(
            """
            UPDATE chat_conversations
            SET folder_names_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [json.dumps(effective_folders), conversation_id],
        )
        return ConversationRecord(
            conversation_id=str(existing[0]),
            title=str(existing[1]),
            folder_names=effective_folders,
        )

    def _create_conversation(
        self,
        *,
        question: str,
        folder_names: list[str],
    ) -> ConversationRecord:
        new_conversation_id = str(uuid4())
        title = self._build_title(question)
        self._database.execute(
            """
            INSERT INTO chat_conversations (id, title, folder_names_json)
            VALUES (?, ?, ?)
            """,
            [new_conversation_id, title, json.dumps(folder_names)],
        )
        return ConversationRecord(
            conversation_id=new_conversation_id,
            title=title,
            folder_names=folder_names,
        )

    def _get_conversation_messages(self, conversation_id: str) -> list[ChatMessage]:
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
            ChatMessage(
                id=str(row[0]),
                role=str(row[1]),
                content=str(row[2]),
                meta=str(row[3]) if row[3] else None,
                sources=[
                    ChatSource(**source_payload)
                    for source_payload in json.loads(str(row[4]) or "[]")
                ],
                created_at=self._serialize_timestamp(row[5]),
            )
            for row in rows
        ]

    def _append_response_message(self, response: ChatResponse) -> None:
        source_count = len(response.sources)
        self._append_message(
            conversation_id=response.conversation_id,
            role="assistant",
            content=response.answer,
            meta=f"{response.model} • {source_count} source{'' if source_count == 1 else 's'}",
            sources=response.sources,
        )

    def _append_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        meta: str | None = None,
        sources: list[ChatSource] | None = None,
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
        serialized_sources = json.dumps(self._serialize_sources(sources or []))
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
                serialized_sources,
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

    def _build_history_block(self, messages: list[ChatMessage]) -> str:
        if not messages:
            return ""

        recent_messages = messages[-8:]
        lines: list[str] = []
        for message in recent_messages:
            speaker = "Assistant" if message.role == "assistant" else "User"
            lines.append(f"{speaker}: {message.content}")

        return "\n".join(lines)

    def _build_title(self, question: str) -> str:
        normalized = " ".join(question.strip().split())
        if len(normalized) <= 64:
            return normalized
        return f"{normalized[:61].rstrip()}..."

    def _postprocess_answer(self, answer: str, query_intents: set[str]) -> str:
        if "earnings" in query_intents:
            return answer.strip()

        irrelevant_markers = ("earnings", "income", "salary", "wages", "payroll")
        negative_markers = (
            "no specific",
            "not mentioned",
            "not provided",
            "not found",
            "not included",
            "missing",
        )

        filtered_lines: list[str] = []
        for line in answer.splitlines():
            lower_line = line.lower()
            if (
                any(marker in lower_line for marker in irrelevant_markers)
                and any(marker in lower_line for marker in negative_markers)
            ):
                continue
            filtered_lines.append(line.rstrip())

        compacted: list[str] = []
        for line in filtered_lines:
            if line or (compacted and compacted[-1]):
                compacted.append(line)

        while compacted:
            last_line = compacted[-1].strip()
            if not last_line:
                compacted.pop()
                continue

            if last_line.endswith((".", "!", "?", ")", "\"")):
                break

            compacted.pop()
            if compacted and compacted[-1].strip().endswith(":"):
                compacted.pop()

        return "\n".join(compacted).strip()

    def _serialize_stream_event(
        self,
        event_type: str,
        payload: dict[str, object],
    ) -> str:
        return json.dumps({"type": event_type, **payload}) + "\n"

    def _serialize_sources(self, sources: list[ChatSource]) -> list[dict[str, object]]:
        return [
            {
                "document_id": source.document_id,
                "folder_name": source.folder_name,
                "document_name": source.document_name,
                "relative_path": source.relative_path,
                "excerpt": source.excerpt,
                "score": source.score,
            }
            for source in sources
        ]

    def _response_payload(self, response: ChatResponse) -> dict[str, object]:
        return {
            "conversation_id": response.conversation_id,
            "conversation_title": response.conversation_title,
            "answer": response.answer,
            "model": response.model,
            "selected_folders": response.selected_folders,
            "sources": self._serialize_sources(response.sources),
        }

    def _normalize_folder_names(self, folder_names: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for folder_name in folder_names:
            cleaned = folder_name.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    def _parse_folder_names(self, payload: object) -> list[str]:
        if payload is None:
            return []
        try:
            parsed = json.loads(str(payload))
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(value) for value in parsed if str(value).strip()]

    def _serialize_timestamp(self, value: object) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
