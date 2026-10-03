import asyncio
from app.clients.jev_client import JevClient
from app.clients.jev_questions import NoulQuestion
from app.config.settings import ValidationThresholds
from app.domain.cv_models import CvClaim
from app.domain.document_models import DocumentSection
from app.domain.validation_models import ClaimCheck, JevEvaluation
from app.validators.base_validator import BaseValidator
from app.validators.evidence_chunker import EvidenceChunker

class CvFaithfulnessValidator(BaseValidator):
    QUESTION = "Is `claim` supported by `source_documents`?"
    TRUE_CRITERIA = "Every fact in the claim appears in the sources, possibly reworded, condensed or using a standard synonym."
    FALSE_CRITERIA = "The claim adds an employer, title, date, degree, certification, metric, tool, skill or achievement that the sources do not contain."

    def __init__(self, jev_client: JevClient, thresholds: ValidationThresholds, chunker: EvidenceChunker) -> None:
        super().__init__(jev_client, thresholds)
        self._chunker = chunker

    @property
    def name(self) -> str:
        return "cv_faithfulness"

    async def validate(self, claims: list[CvClaim], source_sections: list[DocumentSection]) -> list[ClaimCheck]:
        chunks = self._chunker.chunk_sections(source_sections)
        if not claims:
            return []
        if not chunks:
            return [self._check(claim, []) for claim in claims]
        questions = [self._question(claim) for claim in claims]
        evaluations = await asyncio.gather(
            *(self._jev.evaluate({"source_documents": chunk}, questions) for chunk in chunks)
        )
        checks = [self._check(claim, list(evaluations)) for claim in claims]
        self._log_summary(claims=len(checks), unsupported=sum(1 for check in checks if not check.supported))
        return checks

    def _question(self, claim: CvClaim) -> NoulQuestion:
        return NoulQuestion(
            key=claim.id,
            instructions={"claim": claim.text, "question": self.QUESTION},
            true_criteria=self.TRUE_CRITERIA,
            false_criteria=self.FALSE_CRITERIA,
        )

    def _check(self, claim: CvClaim, evaluations: list[JevEvaluation]) -> ClaimCheck:
        probabilities = [evaluation.nouls[claim.id].probability for evaluation in evaluations if claim.id in evaluation.nouls]
        best = max(probabilities, default=0.0)
        return ClaimCheck(
            claim_id=claim.id,
            text=claim.text,
            section=claim.section,
            support_probability=best,
            supported=best >= self._thresholds.claim_supported,
        )
