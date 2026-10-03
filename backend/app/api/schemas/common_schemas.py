from typing import Any
from pydantic import BaseModel

class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}

class ErrorResponse(BaseModel):
    error: ErrorBody

class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    llm_model: str
    jev_model: str
    web_search_enabled: bool
    session_storage: str
