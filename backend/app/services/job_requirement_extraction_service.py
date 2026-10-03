import json
import logging
from app.agents.analysis.prompts import AnalysisPrompts
from app.clients.llm_client import LlmClient
from app.core.exceptions import LlmOutputError
from app.domain.job_models import JobPosting, ParsedJob

logger = logging.getLogger(__name__)

class JobRequirementExtractionService:
    MAX_KEYWORDS = 20

    def __init__(self, llm_client: LlmClient, max_job_chars: int) -> None:
        self._llm = llm_client
        self._max_job_chars = max_job_chars

    async def extract(self, job: JobPosting) -> ParsedJob:
        user_prompt = json.dumps({"job_posting": job.text[: self._max_job_chars]}, ensure_ascii=False)
        parsed = await self._llm.generate_structured(ParsedJob, AnalysisPrompts.JOB_EXTRACTION_SYSTEM, user_prompt)
        cleaned = self._clean(parsed)
        if not cleaned.must_have_requirements and not cleaned.nice_to_have_requirements:
            raise LlmOutputError("No requirements could be extracted from the job posting. Check that the text is the actual job description.")
        logger.info("job_requirements_extracted", extra={"job_id": job.id, "must_haves": len(cleaned.must_have_requirements), "nice_to_haves": len(cleaned.nice_to_have_requirements)})
        return cleaned

    def _clean(self, parsed: ParsedJob) -> ParsedJob:
        return parsed.model_copy(update={
            "must_have_requirements": self._unique(parsed.must_have_requirements),
            "nice_to_have_requirements": self._unique(parsed.nice_to_have_requirements),
            "responsibilities": self._unique(parsed.responsibilities),
            "keywords": self._unique(parsed.keywords)[: self.MAX_KEYWORDS],
        })

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        unique = []
        for item in items:
            cleaned = item.strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                unique.append(cleaned)
        return unique
