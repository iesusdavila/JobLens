import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.dependencies import ServiceContainer
from app.api.error_handlers import ErrorHandlerRegistry
from app.api.middleware import RequestSizeLimitMiddleware
from app.api.routes import analysis, chat, health, sessions
from app.config.settings import Settings, SettingsLoader
from app.core.logging_config import LoggingConfigurator

logger = logging.getLogger(__name__)

class ApplicationFactory:
    API_PREFIX = "/api/v1"

    def __init__(self, settings: Settings | None = None, container: ServiceContainer | None = None) -> None:
        self._settings = settings or (container.settings if container else SettingsLoader().load())
        self._container = container

    def create(self) -> FastAPI:
        LoggingConfigurator(self._settings.log_level).configure()
        app = FastAPI(title="Job Fit Agent API", version="1.0.0", lifespan=self._lifespan)
        app.state.container = self._container or ServiceContainer(self._settings)
        app.add_middleware(CORSMiddleware, allow_origins=self._settings.allowed_origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
        app.add_middleware(RequestSizeLimitMiddleware, max_bytes=self._settings.max_request_bytes)
        ErrorHandlerRegistry().register(app)
        app.include_router(self._api_router())
        return app

    def _api_router(self) -> APIRouter:
        router = APIRouter(prefix=self.API_PREFIX)
        for module in (health, sessions, analysis, chat):
            router.include_router(module.router)
        return router

    @staticmethod
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        container: ServiceContainer = app.state.container
        cleanup_task = asyncio.create_task(container.cleanup_service.run_forever())
        logger.info("backend_started", extra={"llm_provider": container.settings.llm_provider, "llm_model": container.settings.llm_model, "storage": container.settings.session_storage})
        try:
            yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            await container.aclose()

def create_app() -> FastAPI:
    return ApplicationFactory().create()
