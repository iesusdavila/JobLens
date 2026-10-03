import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

class ErrorHandlerRegistry:
    def register(self, app: FastAPI) -> None:
        app.add_exception_handler(AppError, self.handle_app_error)
        app.add_exception_handler(RequestValidationError, self.handle_validation_error)
        app.add_exception_handler(Exception, self.handle_unexpected_error)

    async def handle_app_error(self, request: Request, error: AppError) -> JSONResponse:
        logger.info("request_failed", extra={"path": request.url.path, "error_code": error.error_code, "status": error.status_code})
        return self._response(error.status_code, error.error_code, error.message, error.details)

    async def handle_validation_error(self, request: Request, error: RequestValidationError) -> JSONResponse:
        problems = [{"field": ".".join(str(part) for part in item.get("loc", [])), "message": item.get("msg", "")} for item in error.errors()]
        message = problems[0]["message"] if problems else "The request is invalid."
        return self._response(422, "validation_error", message, {"problems": problems})

    async def handle_unexpected_error(self, request: Request, error: Exception) -> JSONResponse:
        logger.exception("request_crashed", extra={"path": request.url.path})
        return self._response(500, "internal_error", "Unexpected server error. Try again; if it persists, check the backend logs.", {})

    @staticmethod
    def _response(status_code: int, code: str, message: str, details: dict) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message, "details": details}})
