from __future__ import annotations

from datetime import datetime
import json

from app.db.connection import DatabaseManager
from app.repositories.conversations import ConversationRepository
from app.schemas.chat import ChatMessage, ChatResponse, ChatSource
from app.services.chat import (
    ChatService,
    ConversationRecord,
    PreparedChatOutcome,
    RankedChunk,
)
from app.services.library import ChunkRecord
from app.services.ollama import OllamaChatDelta, OllamaChatResult, OllamaServiceError


class FakeChatLibraryService:
    def __init__(self, chunks: list[ChunkRecord] | None = None) -> None:
        self.chunks = list(chunks or [])
        self.calls: list[list[str] | None] = []

    def search_chunks(self, folder_names: list[str] | None = None) -> list[ChunkRecord]:
        self.calls.append(folder_names)
        return list(self.chunks)


class FakeChatOllamaClient:
    def __init__(self) -> None:
        self.chat_model = "chat-model"
        self.embedding_model = "embed-model"
        self.chat_result = OllamaChatResult(
            content="The monthly charge is $12.00.",
            model="chat-model-v2",
        )
        self.stream_deltas = [
            OllamaChatDelta(content="The charge is ", model="chat-model-v2"),
            OllamaChatDelta(content="$12.00.", model="chat-model-v2", done=True),
        ]
        self.embed_vector = [1.0, 0.0]
        self.chat_error: OllamaServiceError | None = None
        self.stream_error: OllamaServiceError | None = None
        self.embed_error: OllamaServiceError | None = None
        self.chat_calls: list[tuple[str, str]] = []
        self.stream_calls: list[tuple[str, str]] = []
        self.embed_calls: list[str] = []

    def chat(self, *, system_prompt: str, user_prompt: str) -> OllamaChatResult:
        self.chat_calls.append((system_prompt, user_prompt))
        if self.chat_error is not None:
            raise self.chat_error
        return self.chat_result

    def chat_stream(self, *, system_prompt: str, user_prompt: str):
        self.stream_calls.append((system_prompt, user_prompt))
        if self.stream_error is not None:
            raise self.stream_error
        yield from self.stream_deltas

    def embed_text(self, question: str) -> list[float]:
        self.embed_calls.append(question)
        if self.embed_error is not None:
            raise self.embed_error
        return self.embed_vector


def make_chunk(
    *,
    chunk_id: str = "chunk-1",
    document_id: str = "doc-1",
    folder_name: str = "Finance",
    document_name: str = "statement.txt",
    relative_path: str = "statement.txt",
    text: str = "Monthly charge $12.00. Renewal date January 15, 2026.",
    chunk_index: int = 0,
    embedding: list[float] | None = None,
) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id=document_id,
        folder_name=folder_name,
        document_name=document_name,
        relative_path=relative_path,
        text=text,
        chunk_index=chunk_index,
        embedding=embedding if embedding is not None else [1.0, 0.0],
        embedding_model="embed-model",
    )


def make_ranked(
    *,
    chunk_id: str = "ranked-1",
    document_id: str = "doc-1",
    folder_name: str = "Finance",
    document_name: str = "statement.txt",
    relative_path: str = "statement.txt",
    text: str = "Monthly charge $12.00. Renewal date January 15, 2026.",
    score: float = 2.0,
    lexical_score: float = 1.5,
    semantic_score: float = 0.6,
) -> RankedChunk:
    return RankedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        folder_name=folder_name,
        document_name=document_name,
        relative_path=relative_path,
        text=text,
        score=score,
        lexical_score=lexical_score,
        semantic_score=semantic_score,
    )


def build_chat_service(
    database: DatabaseManager,
    *,
    chunks: list[ChunkRecord] | None = None,
    ollama_client: FakeChatOllamaClient | None = None,
) -> tuple[ChatService, ConversationRepository, FakeChatLibraryService, FakeChatOllamaClient]:
    repository = ConversationRepository(database)
    library_service = FakeChatLibraryService(chunks)
    ollama = ollama_client or FakeChatOllamaClient()
    return ChatService(repository, library_service, ollama), repository, library_service, ollama


def test_list_get_and_delete_conversation(database: DatabaseManager) -> None:
    service, repository, _, _ = build_chat_service(database)
    conversation = repository.create_conversation(
        title="Subscription review",
        folder_names_json='["Finance"]',
    )
    repository.append_message(
        conversation_id=conversation.conversation_id,
        role="user",
        content="What renews next?",
        meta="Searching 1 folder",
        sources_json="[]",
    )
    repository.append_message(
        conversation_id=conversation.conversation_id,
        role="assistant",
        content="The gym renews on January 15.",
        meta="chat-model • 1 source",
        sources_json='[{"document_id":"doc-1","folder_name":"Finance","document_name":"gym.pdf","relative_path":"gym.pdf","excerpt":"Renewal date January 15.","score":4.2}]',
    )

    listed = service.list_conversations()
    assert listed.conversations[0].folder_names == ["Finance"]
    assert listed.conversations[0].preview == "The gym renews on January 15."

    detail = service.get_conversation(conversation.conversation_id)
    assert detail is not None
    assert detail.conversation.id == conversation.conversation_id
    assert [message.role for message in detail.messages] == ["user", "assistant"]
    assert detail.messages[1].sources[0].document_name == "gym.pdf"
    assert service.get_conversation("missing") is None

    deleted = service.delete_conversation(conversation.conversation_id)
    assert deleted.conversations == []


def test_answer_question_without_indexed_documents_returns_immediate_response(
    database: DatabaseManager,
) -> None:
    service, repository, library, _ = build_chat_service(database, chunks=[])

    response = service.answer_question(question="What renews next?", folder_names=[])

    assert "I don't have any indexed documents yet" in response.answer
    assert library.calls == [None]
    stored_messages = repository.list_messages(response.conversation_id)
    assert [message.role for message in stored_messages] == ["user", "assistant"]
    assert stored_messages[0].meta == "Searching all indexed folders"


def test_answer_question_calls_ollama_and_persists_response(database: DatabaseManager) -> None:
    service, repository, library, ollama = build_chat_service(
        database,
        chunks=[
            make_chunk(
                text=(
                    "Monthly charge $12.00. Renewal date January 15, 2026. "
                    "Auto-pay is active for this subscription."
                )
            )
        ],
    )

    response = service.answer_question(
        question="What is the monthly charge and renewal date?",
        folder_names=[" Finance ", "Finance"],
    )

    assert response.answer == "The monthly charge is $12.00."
    assert response.model == "chat-model-v2"
    assert response.selected_folders == ["Finance"]
    assert response.sources[0].document_id == "doc-1"
    assert "Context:" in ollama.chat_calls[0][1]
    assert library.calls == [["Finance"]]

    detail = service.get_conversation(response.conversation_id)
    assert detail is not None
    assert len(detail.messages) == 2
    assert detail.messages[1].meta == "chat-model-v2 • 1 source"


def test_stream_answer_question_immediate_and_success_paths(database: DatabaseManager) -> None:
    no_docs_service, repository, _, _ = build_chat_service(database, chunks=[])
    immediate_events = [
        json.loads(item)
        for item in no_docs_service.stream_answer_question(
            question="What renews next?",
            folder_names=[],
        )
    ]
    assert [event["type"] for event in immediate_events] == ["start", "final"]
    assert repository.list_messages(immediate_events[-1]["conversation_id"])[-1].role == "assistant"

    good_service, good_repository, _, _ = build_chat_service(
        database,
        chunks=[make_chunk()],
    )
    events = [
        json.loads(item)
        for item in good_service.stream_answer_question(
            question="What is the monthly charge?",
            folder_names=["Finance"],
        )
    ]
    assert [event["type"] for event in events] == ["start", "delta", "delta", "final"]
    assert events[-1]["answer"] == "The charge is $12.00."
    assert len(good_repository.list_messages(events[-1]["conversation_id"])) == 2


def test_stream_answer_question_returns_error_event_on_stream_failure(
    database: DatabaseManager,
) -> None:
    ollama = FakeChatOllamaClient()
    ollama.stream_error = OllamaServiceError("stream unavailable")
    service, repository, _, _ = build_chat_service(
        database,
        chunks=[make_chunk()],
        ollama_client=ollama,
    )

    events = [
        json.loads(item)
        for item in service.stream_answer_question(
            question="What is the monthly charge?",
            folder_names=["Finance"],
        )
    ]

    assert [event["type"] for event in events] == ["start", "error"]
    stored_messages = repository.list_messages(events[0]["conversation_id"])
    assert [message.role for message in stored_messages] == ["user"]


def test_prepare_chat_outcome_off_topic_no_records_and_empty_selection(
    database: DatabaseManager,
    monkeypatch,
) -> None:
    off_topic_service, _, _, _ = build_chat_service(database, chunks=[make_chunk()])
    off_topic = off_topic_service._prepare_chat_outcome(
        question="Tell me a joke about taxes.",
        folder_names=["Finance"],
        conversation_id=None,
    )
    assert off_topic.immediate_response is not None
    assert off_topic.immediate_response.answer.startswith("No relevant records found")

    low_signal_chunk = make_chunk(
        text="Completely unrelated gardening notes.",
        embedding=None,
    )
    no_records_ollama = FakeChatOllamaClient()
    no_records_ollama.embed_error = OllamaServiceError("no embeddings")
    no_records_service, _, _, _ = build_chat_service(
        database,
        chunks=[low_signal_chunk],
        ollama_client=no_records_ollama,
    )
    no_records = no_records_service._prepare_chat_outcome(
        question="What is the monthly charge?",
        folder_names=[],
        conversation_id=None,
    )
    assert no_records.immediate_response is not None
    assert no_records.immediate_response.answer.startswith("No relevant records found")

    empty_selection_service, _, _, _ = build_chat_service(database, chunks=[make_chunk()])
    monkeypatch.setattr(
        empty_selection_service,
        "_rank_chunks",
        lambda **kwargs: [make_ranked()],
    )
    monkeypatch.setattr(
        empty_selection_service,
        "_should_return_no_records",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        empty_selection_service,
        "_select_context_chunks",
        lambda **kwargs: [],
    )
    empty_selection = empty_selection_service._prepare_chat_outcome(
        question="What is the monthly charge?",
        folder_names=["Finance"],
        conversation_id=None,
    )
    assert empty_selection.immediate_response is not None
    assert empty_selection.immediate_response.answer.startswith("No relevant records found")


def test_ranking_selection_and_no_records_helpers(database: DatabaseManager) -> None:
    ollama = FakeChatOllamaClient()
    ollama.embed_error = OllamaServiceError("embedding down")
    service, _, _, _ = build_chat_service(
        database,
        chunks=[],
        ollama_client=ollama,
    )

    ranked = service._rank_chunks(
        question="What is the monthly charge?",
        chunks=[make_chunk(text="Totally unrelated notes.", embedding=None, chunk_index=3)],
    )
    assert len(ranked) == 1
    assert ranked[0].semantic_score == 0.0

    disclaimer = make_ranked(
        chunk_id="disc-1",
        document_id="doc-a",
        text="For informational purposes only. Should not be relied upon.",
        score=1.2,
        lexical_score=1.2,
        semantic_score=0.0,
    )
    duplicate = make_ranked(
        chunk_id="disc-2",
        document_id="doc-a",
        text="For informational purposes only. Should not be relied upon.",
        score=1.1,
        lexical_score=1.1,
        semantic_score=0.0,
    )
    valuable = make_ranked(
        chunk_id="real-1",
        document_id="doc-b",
        text="Monthly charge $12.00. Renewal date January 15, 2026.",
        score=2.5,
        lexical_score=2.0,
        semantic_score=0.6,
    )

    selected = service._select_context_chunks(
        question="What matters?",
        ranked_chunks=[disclaimer, duplicate, valuable],
        limit=2,
    )
    assert [chunk.chunk_id for chunk in selected] == ["real-1"]

    fallback = service._select_context_chunks(
        question="What matters?",
        ranked_chunks=[disclaimer],
        limit=1,
    )
    assert fallback == [disclaimer]

    grounded_history = [
        ChatMessage(
            id="msg-1",
            role="assistant",
            content="Grounded answer",
            sources=[
                ChatSource(
                    document_id="doc-1",
                    folder_name="Finance",
                    document_name="statement.txt",
                    relative_path="statement.txt",
                    excerpt="Monthly charge $12.00.",
                    score=4.0,
                )
            ],
            created_at="2026-04-12T10:00:00",
        )
    ]

    assert service._should_return_no_records(
        question="What about this one?",
        ranked_chunks=[valuable],
        prior_messages=grounded_history,
    ) is False
    assert service._should_return_no_records(
        question="What is the monthly charge?",
        ranked_chunks=[make_ranked(score=0.4, lexical_score=1.1, semantic_score=0.0)],
        prior_messages=[],
    ) is False
    assert service._should_return_no_records(
        question="Summarize this document",
        ranked_chunks=[make_ranked(score=0.3, lexical_score=0.2, semantic_score=0.1)],
        prior_messages=[],
    ) is True
    assert service._build_no_records_response(
        conversation=ConversationRecord(
            conversation_id="conv-1",
            title="A title",
            folder_names=["Finance"],
        ),
        folder_names=["Finance"],
    ).selected_folders == ["Finance"]


def test_prompt_and_serialization_helpers(database: DatabaseManager) -> None:
    service, _, _, _ = build_chat_service(database)
    ranked_chunk = make_ranked()

    default_prompt = service._build_system_prompt(set())
    assert "extract concrete values first" in default_prompt

    intent_prompt = service._build_system_prompt({"priorities", "subscriptions"})
    assert "Pay attention first" in intent_prompt
    assert "recurring plans" in intent_prompt

    prior_messages = [
        ChatMessage(
            id="msg-1",
            role="user",
            content="What matters here?",
            created_at="2026-04-12T10:00:00",
        ),
        ChatMessage(
            id="msg-2",
            role="assistant",
            content="The renewal date is January 15.",
            created_at="2026-04-12T10:01:00",
        ),
    ]
    user_prompt = service._build_user_prompt(
        question="What matters here?",
        query_intents={"priorities", "subscriptions", "earnings", "dates"},
        prior_messages=prior_messages,
        top_chunks=[ranked_chunk],
    )
    assert "Conversation history:" in user_prompt
    assert "Requested fields:" in user_prompt
    assert "subscription review request" in user_prompt
    assert "investment income" in user_prompt

    sources = service._build_sources(
        question="What matters here?",
        top_chunks=[ranked_chunk],
    )
    assert sources[0].score == 2.0

    prepared = PreparedChatOutcome(
        conversation=ConversationRecord(
            conversation_id="conv-1",
            title="A title",
            folder_names=["Finance"],
        ),
        folder_names=["Finance"],
        user_meta="Searching 1 folder",
        query_intents={"dates"},
        sources=sources,
    )
    chat_response = service._build_chat_response(
        prepared=prepared,
        answer="Summary:\nImportant detail.\nTrailing",
        model="chat-model",
    )
    assert chat_response.answer == "Summary:\nImportant detail."

    assert service._postprocess_answer("Income not found", {"earnings"}) == "Income not found"
    assert service._postprocess_answer("Section:\nTrailing", set()) == ""

    ranked = service._build_ranked_chunk(
        question="What is the monthly charge?",
        chunk=make_chunk(),
        query_embedding=[1.0, 0.0],
    )
    assert ranked.score > 0
    assert ranked.semantic_score == 1.0

    assert service._fingerprint_chunk_text("  A  B \n C ") == "a b c"
    assert service._is_low_value_disclaimer(
        make_ranked(
            text="For informational purposes only. Should not be relied upon.",
            score=1.0,
            lexical_score=1.0,
            semantic_score=0.0,
        )
    ) is True
    assert service._is_low_value_disclaimer(
        make_ranked(
            text="Renewal date January 15, 2026.",
            score=1.0,
            lexical_score=1.0,
            semantic_score=0.0,
        )
    ) is False
    assert service._is_low_value_disclaimer(
        make_ranked(
            text="For informational purposes only.",
            score=0.0,
            lexical_score=0.0,
            semantic_score=0.0,
        )
    ) is False

    assert service._build_history_block([]) == ""
    assert "User: What matters here?" in service._build_history_block(prior_messages)
    assert service._build_title(" short title ") == "short title"
    assert service._build_title("x" * 80).endswith("...")

    serialized_event = json.loads(
        service._serialize_stream_event("delta", {"delta": "hello"}).strip()
    )
    assert serialized_event == {"type": "delta", "delta": "hello"}
    assert service._serialize_sources(sources) == [
        {
            "document_id": "doc-1",
            "folder_name": "Finance",
            "document_name": "statement.txt",
            "relative_path": "statement.txt",
            "excerpt": sources[0].excerpt,
            "score": sources[0].score,
        }
    ]
    assert service._response_payload(chat_response)["conversation_id"] == "conv-1"
    assert service._normalize_folder_names([" Finance ", "", "Finance", "Travel "]) == [
        "Finance",
        "Travel",
    ]
    assert service._parse_folder_names(None) == []
    assert service._parse_folder_names("not-json") == []
    assert service._parse_folder_names('{"folder":"Finance"}') == []
    assert service._parse_folder_names('["Finance", "", "Travel"]') == ["Finance", "Travel"]
    assert service._serialize_timestamp(datetime(2026, 4, 12, 9, 30, 0)) == "2026-04-12T09:30:00"
    assert service._serialize_timestamp("raw") == "raw"


def test_existing_conversation_and_message_helpers(database: DatabaseManager) -> None:
    service, repository, _, _ = build_chat_service(database)

    assert service._load_existing_conversation(folder_names=[], conversation_id=None) is None
    assert service._load_existing_conversation(folder_names=[], conversation_id="missing") is None

    created = service._create_conversation(
        question="  Review my travel subscriptions  ",
        folder_names=["Travel"],
    )
    assert created.title == "Review my travel subscriptions"

    loaded_stored = service._load_existing_conversation(
        folder_names=[],
        conversation_id=created.conversation_id,
    )
    assert loaded_stored is not None
    assert loaded_stored.folder_names == ["Travel"]

    loaded_override = service._load_existing_conversation(
        folder_names=["Finance"],
        conversation_id=created.conversation_id,
    )
    assert loaded_override is not None
    assert loaded_override.folder_names == ["Finance"]

    service._append_message(
        conversation_id=created.conversation_id,
        role="user",
        content="Show me the latest renewal.",
        meta="Searching 1 folder",
        sources=[
            ChatSource(
                document_id="doc-1",
                folder_name="Finance",
                document_name="statement.txt",
                relative_path="statement.txt",
                excerpt="Renewal date January 15.",
                score=4.2,
            )
        ],
    )
    conversation_messages = service._get_conversation_messages(created.conversation_id)
    assert conversation_messages[0].sources[0].document_id == "doc-1"

    response = ChatResponse(
        conversation_id=created.conversation_id,
        conversation_title=created.title,
        answer="The latest renewal is January 15.",
        model="chat-model",
        selected_folders=["Finance"],
        sources=conversation_messages[0].sources,
    )
    service._append_response_message(response)

    stored_messages = repository.list_messages(created.conversation_id)
    assert stored_messages[-1].meta == "chat-model • 1 source"
    assert repository.get_conversation_record("missing") is None
