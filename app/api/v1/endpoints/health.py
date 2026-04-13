from fastapi import APIRouter

from app.core.config import settings
from app.deps import DatabaseDep
from app.schemas.health import HealthCheckResponse

router = APIRouter(tags=["health"])


@router.get("/health_check", response_model=HealthCheckResponse)
async def health_check(database: DatabaseDep) -> HealthCheckResponse:
    return HealthCheckResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        database=database.health(),
        ollama={
            "base_url": settings.ollama_base_url,
            "chat_model": settings.ollama_chat_model,
            "embedding_model": settings.ollama_embedding_model,
            "chat_num_ctx": settings.ollama_chat_num_ctx,
        },
    )
