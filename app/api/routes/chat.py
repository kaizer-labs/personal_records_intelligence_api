from fastapi import APIRouter, HTTPException, Request

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ollama import OllamaServiceError

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/answers", response_model=ChatResponse)
async def answer_question(
    payload: ChatRequest,
    request: Request,
) -> ChatResponse:
    try:
        return request.app.state.chat_service.answer_question(
            question=payload.question,
            folder_names=payload.folder_names,
        )
    except OllamaServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
