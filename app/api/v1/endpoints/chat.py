from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.deps import ChatServiceDep
from app.schemas.chat import (
    ChatConversationDetailResponse,
    ChatConversationListResponse,
    ChatRequest,
    ChatResponse,
)
from app.services.ollama import OllamaServiceError

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/conversations", response_model=ChatConversationListResponse)
async def list_conversations(chat_service: ChatServiceDep) -> ChatConversationListResponse:
    return chat_service.list_conversations()


@router.get(
    "/conversations/{conversation_id}",
    response_model=ChatConversationDetailResponse,
)
async def get_conversation(
    conversation_id: str,
    chat_service: ChatServiceDep,
) -> ChatConversationDetailResponse:
    conversation = chat_service.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@router.delete(
    "/conversations/{conversation_id}",
    response_model=ChatConversationListResponse,
)
async def delete_conversation(
    conversation_id: str,
    chat_service: ChatServiceDep,
) -> ChatConversationListResponse:
    return chat_service.delete_conversation(conversation_id)


@router.post("/answers", response_model=ChatResponse)
async def answer_question(
    payload: ChatRequest,
    chat_service: ChatServiceDep,
) -> ChatResponse:
    try:
        return chat_service.answer_question(
            question=payload.question,
            folder_names=payload.folder_names,
            conversation_id=payload.conversation_id,
        )
    except OllamaServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/answers/stream")
async def answer_question_stream(
    payload: ChatRequest,
    chat_service: ChatServiceDep,
) -> StreamingResponse:
    return StreamingResponse(
        chat_service.stream_answer_question(
            question=payload.question,
            folder_names=payload.folder_names,
            conversation_id=payload.conversation_id,
        ),
        media_type="application/x-ndjson",
    )
