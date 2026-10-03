import json
import logging
from pydantic import BaseModel, Field
from app.agents.analysis.prompts import AnalysisPrompts
from app.clients.llm_client import LlmClient
from app.domain.cv_models import TailoredCvDraft
from app.domain.job_models import ParsedJob
from app.domain.profile_models import CandidateProfile
from app.services.cv_fact_guard import CvFactGuard, FactGuardResult

logger = logging.getLogger(__name__)

class TailoringContext(BaseModel):
    parsed_job: ParsedJob
    profile: CandidateProfile
    cv_text: str
    extra_text: str | None = None
    gaps: list[str] = Field(default_factory=list)
    feedback: list[str] = Field(default_factory=list)
    revision_focus: str | None = None
    previous_draft: TailoredCvDraft | None = None

class CvTailoringService:
    def __init__(self, llm_client: LlmClient, fact_guard: CvFactGuard, max_source_chars: int, max_words: int, max_bullets: int) -> None:
        self._llm = llm_client
        self._fact_guard = fact_guard
        self._max_source_chars = max_source_chars
        self._max_words = max_words
        self._max_bullets = max_bullets

    async def draft(self, context: TailoringContext) -> FactGuardResult:
        system_prompt = AnalysisPrompts.CV_TAILORING_SYSTEM.format(max_bullets=self._max_bullets, max_words=self._max_words)
        draft = await self._llm.generate_structured(TailoredCvDraft, system_prompt, self._user_prompt(context))
        result = self._fact_guard.enforce(draft, context.profile)
        logger.info("cv_draft_created", extra={"experiences": len(result.draft.cv.experiences), "changes": len(result.draft.changes), "guard_corrections": len(result.corrections)})
        return result

    def _user_prompt(self, context: TailoringContext) -> str:
        payload: dict[str, object] = {
            "job": context.parsed_job.summary_state(),
            "candidate_profile": context.profile.model_dump(exclude={"experiences": {"__all__": {"source_refs"}}, "projects": {"__all__": {"source_refs"}}}),
            "source_documents": {
                "cv": context.cv_text[: self._max_source_chars],
                "extra_document": context.extra_text[: self._max_source_chars] if context.extra_text else None,
            },
            "gaps_not_to_add": context.gaps,
        }
        if context.feedback:
            payload["validator_feedback_to_fix"] = context.feedback
        if context.revision_focus:
            payload["revision_focus"] = context.revision_focus
        if context.previous_draft:
            payload["previous_draft"] = context.previous_draft.cv.model_dump()
        return json.dumps(payload, ensure_ascii=False)
