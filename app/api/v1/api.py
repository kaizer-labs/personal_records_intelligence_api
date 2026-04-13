from fastapi import APIRouter

from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.library import router as library_router

# The package is versioned for code organization first.
# URL version prefixes can be added later without another router reshuffle.
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(library_router)
api_router.include_router(chat_router)
