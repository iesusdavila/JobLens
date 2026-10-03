from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.api.dependencies import get_chat_service
from app.api.schemas.chat_schemas import ChatRequest, ChatResponse
from app.services.chat_service import ApplicationChatService

router = APIRouter(prefix="/sessions", tags=["chat"])

@router.post("/{session_id}/chat", response_model=ChatResponse)
async def chat(session_id: str, request: ChatRequest, service: ApplicationChatService = Depends(get_chat_service)) -> ChatResponse | StreamingResponse:
    turn = service.prepare(session_id, request.message, request.job_id)
    if request.stream:
        return StreamingResponse(service.stream(turn), media_type="text/plain; charset=utf-8")
    reply = await service.reply(turn)
    return ChatResponse(reply=reply.reply, sources=reply.sources, scope=reply.scope)
