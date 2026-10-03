import asyncio
import logging
from app.domain.document_models import ParsedDocument
from app.domain.job_models import JobPosting, ParsedJob
from app.domain.profile_models import CandidateProfile
from app.domain.session_models import CandidatePreferences
from app.domain.validation_models import FitAnalysis, FitValidationBundle
from app.validators.ats_alignment_validator import AtsAlignmentValidator
from app.validators.fit_dimension_validator import FitDimensionValidator
from app.validators.fit_score_aggregator import FitScoreAggregator
from app.validators.red_flag_validator import RedFlagValidator
from app.validators.requirement_match_validator import RequirementMatchValidator
from app.validators.seniority_validator import SeniorityValidator

logger = logging.getLogger(__name__)

class FitEvaluationService:
    def __init__(
        self,
        requirement_validator: RequirementMatchValidator,
        dimension_validator: FitDimensionValidator,
        seniority_validator: SeniorityValidator,
        red_flag_validator: RedFlagValidator,
        ats_validator: AtsAlignmentValidator,
        aggregator: FitScoreAggregator,
    ) -> None:
        self._requirement_validator = requirement_validator
        self._dimension_validator = dimension_validator
        self._seniority_validator = seniority_validator
        self._red_flag_validator = red_flag_validator
        self._ats_validator = ats_validator
        self._aggregator = aggregator

    async def evaluate(
        self,
        job: JobPosting,
        parsed_job: ParsedJob,
        profile: CandidateProfile,
        cv: ParsedDocument,
        extra: ParsedDocument | None,
        preferences: CandidatePreferences,
    ) -> FitAnalysis:
        evidence = cv.sections + (extra.sections if extra else [])
        requirements, dimensions, seniority, red_flags, ats_original = await asyncio.gather(
            self._requirement_validator.validate(parsed_job, evidence),
            self._dimension_validator.validate(parsed_job, profile),
            self._seniority_validator.validate(parsed_job, profile),
            self._red_flag_validator.validate(job, parsed_job, profile, preferences),
            self._ats_validator.validate(parsed_job, cv.text),
        )
        bundle = FitValidationBundle(requirements=requirements, dimensions=dimensions, seniority=seniority, red_flags=red_flags, ats_original=ats_original)
        analysis = self._aggregator.aggregate(bundle)
        logger.info("fit_evaluated", extra={"job_id": job.id, "overall_score": analysis.overall_score, "recommendation": analysis.recommendation.value})
        return analysis
