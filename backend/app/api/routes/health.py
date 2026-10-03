from fastapi import APIRouter, Depends
from app.api.dependencies import get_settings
from app.api.schemas.common_schemas import HealthResponse
from app.config.settings import Settings

router = APIRouter(tags=["health"])

@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        jev_model=settings.typesafe_default_model,
        web_search_enabled=settings.enable_web_search,
        session_storage=settings.session_storage,
    )
