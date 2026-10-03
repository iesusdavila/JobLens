import asyncio
import logging
from app.domain.session_models import utc_now
from app.repositories.session_repository import SessionLockRegistry, SessionRepository
from app.services.cv_export_service import CvExportService

logger = logging.getLogger(__name__)

class SessionCleanupService:
    def __init__(self, repository: SessionRepository, export_service: CvExportService, locks: SessionLockRegistry, interval_seconds: int) -> None:
        self._repository = repository
        self._export_service = export_service
        self._locks = locks
        self._interval_seconds = interval_seconds

    def purge_expired(self) -> int:
        expired = self._repository.delete_expired(utc_now())
        for session_id in expired:
            self._export_service.drop_session(session_id)
            self._locks.release(session_id)
        if expired:
            logger.info("sessions_expired", extra={"count": len(expired)})
        return len(expired)

    async def run_forever(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            self.purge_expired()
