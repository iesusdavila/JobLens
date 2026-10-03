import asyncio
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from app.core.exceptions import SessionNotFoundError
from app.domain.session_models import Session, utc_now

class SessionRepository(ABC):
    SESSION_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")

    def __init__(self, ttl: timedelta) -> None:
        self._ttl = ttl

    def get(self, session_id: str) -> Session:
        self._ensure_valid_id(session_id)
        session = self._load(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session '{session_id}' does not exist or has expired. Create a new session.")
        if session.is_expired(self._ttl, utc_now()):
            self.delete(session_id)
            raise SessionNotFoundError(f"Session '{session_id}' has expired and its documents were deleted. Create a new session.")
        return session

    def save(self, session: Session) -> None:
        self._ensure_valid_id(session.id)
        session.touch()
        self._store(session)

    def delete_expired(self, now: datetime) -> list[str]:
        expired = [session_id for session_id in self.list_ids() if self._is_expired(session_id, now)]
        for session_id in expired:
            self.delete(session_id)
        return expired

    def _is_expired(self, session_id: str, now: datetime) -> bool:
        session = self._load(session_id)
        return session is None or session.is_expired(self._ttl, now)

    def _ensure_valid_id(self, session_id: str) -> None:
        if not self.SESSION_ID_PATTERN.match(session_id):
            raise SessionNotFoundError(f"Session '{session_id}' does not exist.")

    @abstractmethod
    def delete(self, session_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_ids(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def _load(self, session_id: str) -> Session | None:
        raise NotImplementedError

    @abstractmethod
    def _store(self, session: Session) -> None:
        raise NotImplementedError

class SessionLockRegistry:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    def release(self, session_id: str) -> None:
        self._locks.pop(session_id, None)
