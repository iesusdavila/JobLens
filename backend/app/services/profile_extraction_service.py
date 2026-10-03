import json
import logging
import re
from app.agents.analysis.prompts import AnalysisPrompts
from app.clients.llm_client import LlmClient
from app.core.exceptions import DocumentParsingError
from app.domain.document_models import DocumentSection, ParsedDocument
from app.domain.profile_models import CandidateProfile

logger = logging.getLogger(__name__)

class SourceReferenceLocator:
    TOKEN_PATTERN = re.compile(r"[\w+#.]{3,}", re.UNICODE)
    MIN_OVERLAP = 0.3

    def locate(self, text: str, sections: list[DocumentSection]) -> list[str]:
        tokens = self._tokens(text)
        if not tokens:
            return []
        scored = [(len(tokens & self._tokens(section.text)) / len(tokens), section.id) for section in sections]
        best_score, best_id = max(scored, default=(0.0, ""))
        return [best_id] if best_score >= self.MIN_OVERLAP else []

    def _tokens(self, text: str) -> set[str]:
        return {token.lower() for token in self.TOKEN_PATTERN.findall(text)}

class ProfileExtractionService:
    def __init__(self, llm_client: LlmClient, locator: SourceReferenceLocator, max_source_chars: int) -> None:
        self._llm = llm_client
        self._locator = locator
        self._max_source_chars = max_source_chars

    async def extract(self, cv: ParsedDocument, extra: ParsedDocument | None) -> CandidateProfile:
        user_prompt = json.dumps(
            {"cv": cv.text[: self._max_source_chars], "extra_document": extra.text[: self._max_source_chars] if extra else None},
            ensure_ascii=False,
        )
        profile = await self._llm.generate_structured(CandidateProfile, AnalysisPrompts.PROFILE_EXTRACTION_SYSTEM, user_prompt)
        if profile.is_empty:
            raise DocumentParsingError("The CV could not be interpreted: no experience, skills, projects or education were found. Check the uploaded file.")
        traced = self._attach_sources(profile, cv.sections + (extra.sections if extra else []))
        logger.info("candidate_profile_parsed", extra={"experiences": len(traced.experiences), "skills": len(traced.skills)})
        return traced

    def _attach_sources(self, profile: CandidateProfile, sections: list[DocumentSection]) -> CandidateProfile:
        traced = profile.model_copy(deep=True)
        for entry in traced.experiences:
            entry.source_refs = self._refs([entry.employer, entry.title, *entry.highlights], sections)
        for project in traced.projects:
            project.source_refs = self._refs([project.name, *project.highlights], sections)
        return traced

    def _refs(self, texts: list[str], sections: list[DocumentSection]) -> list[str]:
        refs: list[str] = []
        for text in texts:
            for ref in self._locator.locate(text, sections):
                if ref not in refs:
                    refs.append(ref)
        return refs
