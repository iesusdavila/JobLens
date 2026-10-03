from datetime import timedelta
from app.domain.session_models import Session
from app.repositories.session_repository import SessionRepository

class MemorySessionRepository(SessionRepository):
    def __init__(self, ttl: timedelta) -> None:
        super().__init__(ttl)
        self._sessions: dict[str, Session] = {}

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list_ids(self) -> list[str]:
        return list(self._sessions)

    def _load(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        return session.model_copy(deep=True) if session else None

    def _store(self, session: Session) -> None:
        self._sessions[session.id] = session.model_copy(deep=True)
