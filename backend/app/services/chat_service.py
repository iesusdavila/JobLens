import json
import logging
from collections.abc import AsyncIterator
from pydantic import BaseModel
from app.agents.chat.chat_agent import ChatAgent, ChatReplyCollector
from app.agents.chat.prompts import ChatPrompts
from app.clients.llm_client import LLM_TRANSPORT_ERRORS
from app.core.exceptions import ChatError, InvalidRequestError
from app.domain.analysis_models import JobAnalysisResult
from app.domain.enums import ChatRole
from app.domain.job_models import JobPosting
from app.domain.session_models import ChatMessage, Session
from app.repositories.session_repository import SessionLockRegistry, SessionRepository

logger = logging.getLogger(__name__)

class ChatTurn(BaseModel):
    session_id: str
    scope: str
    message: str
    system_prompt: str
    history: list[ChatMessage]

class ChatReply(BaseModel):
    reply: str
    sources: list[str]
    scope: str

class ChatContextBuilder:
    MAX_CV_CHARS = 12000
    MAX_JOB_CHARS = 6000
    MAX_JOBS = 6

    def build(self, session: Session, job_id: str | None) -> str:
        jobs = [session.find_job(job_id)] if job_id else [job for job in session.jobs if job.is_ready][: self.MAX_JOBS]
        payload = {
            "candidate_cv": session.cv.text[: self.MAX_CV_CHARS] if session.cv else None,
            "candidate_extra_document": session.extra_document.text[: self.MAX_CV_CHARS] if session.extra_document else None,
            "candidate_preferences": session.preferences.model_dump(exclude_none=True),
            "jobs": [self._job_context(job, session.analysis.results.get(job.id)) for job in jobs],
            "ranking": [entry.model_dump(include={"rank", "job_name", "overall_score", "recommendation"}) for entry in session.analysis.ranking],
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _job_context(self, job: JobPosting, result: JobAnalysisResult | None) -> dict[str, object]:
        context: dict[str, object] = {"job_id": job.id, "name": job.display_name, "url": job.url}
        if result is None or result.parsed_job is None:
            context["posting_text"] = job.text[: self.MAX_JOB_CHARS]
            return context
        context["parsed_job"] = result.parsed_job.model_dump()
        if result.fit:
            context["fit_analysis"] = {
                "overall_score": result.fit.overall_score,
                "recommendation": result.fit.recommendation.value,
                "reasons": result.fit.recommendation_reasons,
                "strengths": result.fit.strengths,
                "gaps": result.fit.gaps,
                "red_flags": [flag.description for flag in result.fit.red_flags if flag.triggered],
                "seniority": result.fit.seniority.match.value,
            }
        if result.markdown_preview:
            context["tailored_cv"] = result.markdown_preview
        return context

class ApplicationChatService:
    ALL_JOBS_SCOPE = "all"

    def __init__(
        self,
        repository: SessionRepository,
        agent: ChatAgent,
        context_builder: ChatContextBuilder,
        locks: SessionLockRegistry,
        history_window: int,
    ) -> None:
        self._repository = repository
        self._agent = agent
        self._context_builder = context_builder
        self._locks = locks
        self._history_window = history_window

    def prepare(self, session_id: str, message: str, job_id: str | None) -> ChatTurn:
        if not message.strip():
            raise InvalidRequestError("The chat message is empty.")
        session = self._repository.get(session_id)
        scope = job_id or self.ALL_JOBS_SCOPE
        rule = ChatPrompts.WEB_SEARCH_ENABLED if self._agent.web_search_enabled else ChatPrompts.WEB_SEARCH_DISABLED
        system_prompt = ChatPrompts.SYSTEM.format(web_search_rule=rule, context=self._context_builder.build(session, job_id))
        history = session.chat_histories.get(scope, [])[-self._history_window:]
        return ChatTurn(session_id=session_id, scope=scope, message=message.strip(), system_prompt=system_prompt, history=history)

    async def stream(self, turn: ChatTurn) -> AsyncIterator[str]:
        collector = ChatReplyCollector()
        try:
            async for text in self._agent.stream(turn.system_prompt, turn.history, turn.message, collector):
                yield text
        except LLM_TRANSPORT_ERRORS as error:
            logger.warning("chat_failed", extra={"session_id": turn.session_id, "error_type": type(error).__name__})
            yield "\n\n[The assistant is temporarily unavailable. Please try again in a moment.]"
            return
        await self._persist(turn, collector)

    async def reply(self, turn: ChatTurn) -> ChatReply:
        collector = ChatReplyCollector()
        try:
            async for _ in self._agent.stream(turn.system_prompt, turn.history, turn.message, collector):
                pass
        except LLM_TRANSPORT_ERRORS as error:
            raise ChatError("The assistant is temporarily unavailable. Check the LLM credentials in .env and try again.") from error
        await self._persist(turn, collector)
        return ChatReply(reply=collector.text, sources=collector.sources, scope=turn.scope)

    async def _persist(self, turn: ChatTurn, collector: ChatReplyCollector) -> None:
        async with self._locks.lock_for(turn.session_id):
            session = self._repository.get(turn.session_id)
            history = session.chat_histories.setdefault(turn.scope, [])
            history.append(ChatMessage(role=ChatRole.USER, content=turn.message))
            history.append(ChatMessage(role=ChatRole.ASSISTANT, content=collector.text, sources=collector.sources))
            session.chat_histories[turn.scope] = history[-self._history_window * 2:]
            self._repository.save(session)
        logger.info("chat_turn_completed", extra={"session_id": turn.session_id, "scope": turn.scope, "sources": len(collector.sources)})
