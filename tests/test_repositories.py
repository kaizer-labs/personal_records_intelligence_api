from __future__ import annotations

import json

from app.db.connection import DatabaseManager
from app.repositories.conversations import ConversationRepository
from app.repositories.documents import DocumentRepository


def test_document_repository_round_trip(database: DatabaseManager) -> None:
    repository = DocumentRepository(database)

    folder_id = repository.upsert_folder("Finance", "browser_upload")
    assert repository.get_folder_id("Finance") == folder_id

    first_document_id = repository.upsert_document(
        folder_id=folder_id,
        filename="statement.txt",
        relative_path="statement.txt",
        storage_path="/tmp/statement.txt",
        media_type="text/plain",
        sha256="hash-1",
        extracted_text="First version",
        char_count=13,
        chunk_count=1,
    )
    same_document_id = repository.upsert_document(
        folder_id=folder_id,
        filename="statement.txt",
        relative_path="statement.txt",
        storage_path="/tmp/statement-v2.txt",
        media_type="text/plain",
        sha256="hash-2",
        extracted_text="Updated version",
        char_count=15,
        chunk_count=2,
    )

    assert same_document_id == first_document_id
    assert repository.get_document_id(folder_id, "statement.txt") == first_document_id

    chunk_records = repository.replace_document_chunks(
        first_document_id,
        ["Monthly charge $12.00", "Renewal date January 15, 2026"],
    )
    repository.store_chunk_embedding(
        chunk_id=chunk_records[0][0],
        embedding_model="embed-model",
        embedding=[0.1, 0.2, 0.3],
    )

    repository.touch_folder(folder_id)

    folders = repository.list_folders()
    assert len(folders) == 1
    assert folders[0].name == "Finance"

    documents = repository.list_documents()
    assert len(documents) == 1
    assert documents[0].relative_path == "statement.txt"
    assert documents[0].chunk_count == 2

    location = repository.get_document_location(first_document_id)
    assert location is not None
    assert location.storage_path == "/tmp/statement-v2.txt"

    file_record = repository.get_document_file(first_document_id)
    assert file_record is not None
    assert file_record.filename == "statement.txt"

    folder_documents = repository.list_folder_documents(folder_id)
    assert [item.document_id for item in folder_documents] == [first_document_id]

    stored_documents = repository.list_stored_folder_documents(folder_id)
    assert stored_documents[0].relative_path == "statement.txt"

    search_all = repository.search_chunks(embedding_model="embed-model")
    assert len(search_all) == 2
    assert json.loads(search_all[0].embedding_json or "[]") == [0.1, 0.2, 0.3]
    assert search_all[1].embedding_json is None

    search_filtered = repository.search_chunks(
        embedding_model="embed-model",
        folder_names=["Finance"],
    )
    assert [chunk.chunk_id for chunk in search_filtered] == [
        chunk_records[0][0],
        chunk_records[1][0],
    ]

    assert repository.count_documents(folder_id) == 1

    repository.delete_document_tree(first_document_id)
    assert repository.get_document_location(first_document_id) is None
    assert repository.get_document_file(first_document_id) is None
    assert repository.count_documents(folder_id) == 0

    repository.delete_folder(folder_id)
    assert repository.list_folders() == []


def test_conversation_repository_round_trip(database: DatabaseManager) -> None:
    repository = ConversationRepository(database)

    conversation = repository.create_conversation(
        title="Review my subscriptions",
        folder_names_json='["Finance"]',
    )
    assert conversation.title == "Review my subscriptions"

    repository.append_message(
        conversation_id=conversation.conversation_id,
        role="user",
        content="What renewals are coming up?",
        meta="Searching 1 folder",
        sources_json="[]",
    )
    repository.append_message(
        conversation_id=conversation.conversation_id,
        role="assistant",
        content="The gym renews on January 15.",
        meta="qwen • 1 source",
        sources_json='[{"document_id":"doc-1","folder_name":"Finance","document_name":"gym.pdf","relative_path":"gym.pdf","excerpt":"Renewal date January 15.","score":4.5}]',
    )

    listed = repository.list_conversations()
    assert len(listed) == 1
    assert listed[0].conversation_id == conversation.conversation_id
    assert listed[0].message_count == 2
    assert listed[0].preview == "The gym renews on January 15."

    loaded = repository.get_conversation(conversation.conversation_id)
    assert loaded is not None
    assert loaded.preview == "The gym renews on January 15."

    messages = repository.list_messages(conversation.conversation_id)
    assert [message.role for message in messages] == ["user", "assistant"]

    record = repository.get_conversation_record(conversation.conversation_id)
    assert record is not None
    assert record.folder_names_json == '["Finance"]'

    repository.update_conversation_folders(
        conversation.conversation_id,
        '["Finance","Travel"]',
    )
    updated = repository.get_conversation_record(conversation.conversation_id)
    assert updated is not None
    assert updated.folder_names_json == '["Finance","Travel"]'

    repository.delete_conversation(conversation.conversation_id)
    assert repository.get_conversation(conversation.conversation_id) is None
    assert repository.list_messages(conversation.conversation_id) == []

