import os
from datetime import timedelta
from pathlib import Path
from pydantic import ValidationError
from app.domain.session_models import Session
from app.repositories.session_repository import SessionRepository

class FileSessionRepository(SessionRepository):
    def __init__(self, ttl: timedelta, storage_path: Path) -> None:
        super().__init__(ttl)
        self._storage_path = storage_path
        self._storage_path.mkdir(parents=True, exist_ok=True)

    def delete(self, session_id: str) -> None:
        self._path(session_id).unlink(missing_ok=True)

    def list_ids(self) -> list[str]:
        return [path.stem for path in self._storage_path.glob("*.json")]

    def _load(self, session_id: str) -> Session | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        try:
            return Session.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError:
            path.unlink(missing_ok=True)
            return None

    def _store(self, session: Session) -> None:
        path = self._path(session.id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(session.model_dump_json(), encoding="utf-8")
        os.replace(temporary, path)

    def _path(self, session_id: str) -> Path:
        return self._storage_path / f"{session_id}.json"
