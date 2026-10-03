from starlette.types import ASGIApp, Receive, Scope, Send
from fastapi.responses import JSONResponse

class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self._declared_size(scope) > self._max_bytes:
            response = JSONResponse(
                status_code=413,
                content={"error": {"code": "request_too_large", "message": f"The request exceeds {self._max_bytes // (1024 * 1024)} MB.", "details": {}}},
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    @staticmethod
    def _declared_size(scope: Scope) -> int:
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                return int(value) if value.isdigit() else 0
        return 0
