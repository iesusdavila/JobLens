import asyncio
import logging
from app.domain.cv_models import TailoredCvDraft
from app.domain.document_models import DocumentSection
from app.domain.job_models import ParsedJob
from app.domain.validation_models import AtsAlignment, CvValidationReport
from app.services.cv_claims import CvClaimExtractor
from app.services.cv_templates.markdown_renderer import MarkdownCvRenderer
from app.validators.ats_alignment_validator import AtsAlignmentValidator
from app.validators.cv_faithfulness_validator import CvFaithfulnessValidator
from app.validators.cv_quality_validator import CvQualityValidator

logger = logging.getLogger(__name__)

class CvEvaluationService:
    def __init__(
        self,
        faithfulness_validator: CvFaithfulnessValidator,
        ats_validator: AtsAlignmentValidator,
        quality_validator: CvQualityValidator,
        claim_extractor: CvClaimExtractor,
        markdown_renderer: MarkdownCvRenderer,
        min_ats_improvement: float,
    ) -> None:
        self._faithfulness_validator = faithfulness_validator
        self._ats_validator = ats_validator
        self._quality_validator = quality_validator
        self._claim_extractor = claim_extractor
        self._markdown_renderer = markdown_renderer
        self._min_ats_improvement = min_ats_improvement

    async def evaluate(self, parsed_job: ParsedJob, draft: TailoredCvDraft, sources: list[DocumentSection], ats_original: AtsAlignment) -> CvValidationReport:
        claims = self._claim_extractor.extract(draft.cv)
        markdown = self._markdown_renderer.render(draft.cv)
        claim_checks, ats_tailored, quality = await asyncio.gather(
            self._faithfulness_validator.validate(claims, sources),
            self._ats_validator.validate(parsed_job, markdown),
            self._quality_validator.validate(parsed_job, draft.cv, markdown),
        )
        report = CvValidationReport(
            claim_checks=claim_checks,
            ats_original=ats_original,
            ats_tailored=ats_tailored,
            ats_improved=ats_tailored.score - ats_original.score >= self._min_ats_improvement,
            quality=quality,
        )
        logger.info("cv_validated", extra={"claims": len(claim_checks), "unsupported": len(report.unsupported_claims), "ats_improved": report.ats_improved, "quality_passed": quality.passed})
        return report
