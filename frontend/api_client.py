from collections.abc import Iterator
from typing import Any
import httpx

class ApiError(Exception):
    def __init__(self, message: str, code: str = "error", status: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status

class ApiClient:
    API_PREFIX = "/api/v1"

    def __init__(self, base_url: str, timeout: float) -> None:
        self._client = httpx.Client(base_url=f"{base_url.rstrip('/')}{self.API_PREFIX}", timeout=timeout)

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def create_session(self, preferences: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", "/sessions", json={"preferences": preferences})

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/sessions/{session_id}")

    def update_preferences(self, session_id: str, preferences: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/sessions/{session_id}/preferences", json=preferences)

    def upload_documents(
        self,
        session_id: str,
        cv_file: tuple[str, bytes] | None,
        cv_text: str | None,
        extra_file: tuple[str, bytes] | None,
        extra_text: str | None,
    ) -> dict[str, Any]:
        files = {name: value for name, value in (("cv_file", cv_file), ("extra_file", extra_file)) if value}
        data = {name: value for name, value in (("cv_text", cv_text), ("extra_text", extra_text)) if value and value.strip()}
        return self._request("POST", f"/sessions/{session_id}/documents", files=files or None, data=data or None)

    def add_jobs(self, session_id: str, jobs: list[dict[str, str]]) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/jobs", json={"jobs": jobs})

    def update_job_text(self, session_id: str, job_id: str, text: str) -> dict[str, Any]:
        return self._request("PUT", f"/sessions/{session_id}/jobs/{job_id}/text", json={"text": text})

    def remove_job(self, session_id: str, job_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/sessions/{session_id}/jobs/{job_id}")

    def start_analysis(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/analyze", params={"background": True})

    def get_status(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/sessions/{session_id}/status")

    def get_results(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/sessions/{session_id}/results")

    def download_cv(self, session_id: str, job_id: str, export_format: str) -> bytes:
        response = self._send("GET", f"/sessions/{session_id}/jobs/{job_id}/cv", params={"format": export_format})
        return response.content

    def chat(self, session_id: str, message: str, job_id: str | None) -> dict[str, Any]:
        return self._request("POST", f"/sessions/{session_id}/chat", json={"message": message, "job_id": job_id, "stream": False})

    def stream_chat(self, session_id: str, message: str, job_id: str | None) -> Iterator[str]:
        payload = {"message": message, "job_id": job_id, "stream": True}
        try:
            with self._client.stream("POST", f"/sessions/{session_id}/chat", json=payload) as response:
                if response.status_code >= 400:
                    response.read()
                    raise self._error(response)
                yield from response.iter_text()
        except httpx.HTTPError as error:
            raise ApiError(f"The backend is unreachable: {error}") from error

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._send(method, path, **kwargs)
        return response.json() if response.content else {}

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise ApiError(f"The backend is unreachable at {self._client.base_url}. Start it and retry.") from error
        if response.status_code >= 400:
            raise self._error(response)
        return response

    @staticmethod
    def _error(response: httpx.Response) -> ApiError:
        try:
            body = response.json().get("error", {})
        except ValueError:
            body = {}
        return ApiError(body.get("message") or f"HTTP {response.status_code}", body.get("code", "error"), response.status_code)
