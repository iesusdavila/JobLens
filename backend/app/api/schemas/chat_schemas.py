from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    job_id: str | None = None
    stream: bool = False

class ChatResponse(BaseModel):
    reply: str
    sources: list[str]
    scope: str
