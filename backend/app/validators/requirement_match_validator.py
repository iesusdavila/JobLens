import asyncio
from app.clients.jev_client import JevClient
from app.clients.jev_questions import NoulQuestion
from app.config.settings import ValidationThresholds
from app.domain.document_models import DocumentSection
from app.domain.enums import RequirementVerdict
from app.domain.job_models import JobRequirement, ParsedJob
from app.domain.validation_models import JevEvaluation, NoulResult, RequirementAssessment
from app.validators.base_validator import BaseValidator
from app.validators.evidence_chunker import EvidenceChunker

class RequirementMatchValidator(BaseValidator):
    QUESTION = "Does `candidate_evidence` show that the candidate satisfies `requirement`? Direct experience, the same tool under another name, or clearly equivalent work counts."
    TRUE_CRITERIA = "The evidence shows the candidate has done, used or studied what the requirement asks for."
    FALSE_CRITERIA = "Nothing in the evidence shows the candidate has what the requirement asks for."

    def __init__(self, jev_client: JevClient, thresholds: ValidationThresholds, chunker: EvidenceChunker) -> None:
        super().__init__(jev_client, thresholds)
        self._chunker = chunker

    @property
    def name(self) -> str:
        return "requirement_match"

    async def validate(self, parsed_job: ParsedJob, evidence_sections: list[DocumentSection]) -> list[RequirementAssessment]:
        requirements = parsed_job.requirements()
        chunks = self._chunker.chunk_sections(evidence_sections)
        if not requirements or not chunks:
            return [self._assess(requirement, []) for requirement in requirements]
        questions = [self._question(requirement) for requirement in requirements]
        evaluations = await asyncio.gather(
            *(self._jev.evaluate(self._state(parsed_job, chunk), questions) for chunk in chunks)
        )
        assessments = [self._assess(requirement, list(evaluations)) for requirement in requirements]
        self._log_summary(
            requirements=len(assessments),
            met=sum(1 for item in assessments if item.verdict == RequirementVerdict.MET),
            chunks=len(chunks),
        )
        return assessments

    def _question(self, requirement: JobRequirement) -> NoulQuestion:
        return NoulQuestion(
            key=requirement.id,
            instructions={"requirement": requirement.text, "question": self.QUESTION},
            true_criteria=self.TRUE_CRITERIA,
            false_criteria=self.FALSE_CRITERIA,
        )

    def _state(self, parsed_job: ParsedJob, chunk: str) -> dict[str, object]:
        return {
            "job_title": parsed_job.title,
            "job_responsibilities": parsed_job.responsibilities[:8],
            "candidate_evidence": chunk,
        }

    def _assess(self, requirement: JobRequirement, evaluations: list[JevEvaluation]) -> RequirementAssessment:
        results = [evaluation.nouls[requirement.id] for evaluation in evaluations if requirement.id in evaluation.nouls]
        best = max(results, key=lambda result: result.probability, default=NoulResult(probability=0.0, confidence=0.0))
        return RequirementAssessment(
            requirement_id=requirement.id,
            text=requirement.text,
            priority=requirement.priority,
            met_probability=best.probability,
            confidence=best.confidence,
            verdict=self._verdict(best.probability),
            low_confidence=self._is_low_confidence(best.confidence),
        )

    def _verdict(self, probability: float) -> RequirementVerdict:
        if probability >= self._thresholds.requirement_met:
            return RequirementVerdict.MET
        if probability >= self._thresholds.requirement_partial:
            return RequirementVerdict.PARTIAL
        return RequirementVerdict.MISSING
