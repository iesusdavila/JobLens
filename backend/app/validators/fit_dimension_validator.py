from app.clients.jev_questions import ScoreQuestion
from app.domain.enums import FitDimension
from app.domain.job_models import ParsedJob
from app.domain.profile_models import CandidateProfile
from app.domain.validation_models import DimensionAssessment, JevEvaluation
from app.validators.base_validator import BaseValidator

class FitDimensionValidator(BaseValidator):
    RUBRICS: dict[FitDimension, tuple[str, list[str]]] = {
        FitDimension.TECHNICAL: (
            "How well do the technical skills shown in `candidate_profile` match the technical demands of `job`?",
            [
                "No overlap with the technical core of the job",
                "Little overlap, most technical demands are unproven",
                "Partial overlap, some core technical demands are shown",
                "Strong overlap, nearly all core technical demands are shown",
                "Complete overlap with depth beyond what the job asks",
            ],
        ),
        FitDimension.DOMAIN: (
            "How closely does the industry and business domain experience in `candidate_profile` match the domain of `job`?",
            [
                "Unrelated domain with no transferable context",
                "Different domain with little transferable context",
                "Adjacent domain with useful transferable context",
                "Same or very close domain",
                "Same domain with deep, repeated experience",
            ],
        ),
        FitDimension.TOOLS: (
            "How well do the tools, platforms and technology stack used in `candidate_profile` match the stack named in `job`?",
            [
                "None of the job's tools appear in the profile",
                "A few minor tools match",
                "About half of the important tools match",
                "Most important tools match",
                "All important tools match with hands-on use",
            ],
        ),
        FitDimension.SOFT_SKILLS: (
            "How well does `candidate_profile` show the communication, collaboration and ownership the responsibilities in `job` require?",
            [
                "No evidence of the required soft skills",
                "Weak or generic evidence",
                "Some concrete evidence",
                "Clear concrete evidence for most of them",
                "Strong concrete evidence for all of them, including leading others",
            ],
        ),
    }

    @property
    def name(self) -> str:
        return "fit_dimension"

    async def validate(self, parsed_job: ParsedJob, profile: CandidateProfile) -> list[DimensionAssessment]:
        questions = [
            ScoreQuestion(key=dimension.value, instructions=instructions, levels=levels)
            for dimension, (instructions, levels) in self.RUBRICS.items()
        ]
        state = {"job": parsed_job.summary_state(), "candidate_profile": profile.compact_state()}
        evaluation = await self._jev.evaluate(state, questions)
        assessments = [self._assess(dimension, evaluation) for dimension in self.RUBRICS]
        self._log_summary(dimensions={item.dimension.value: round(item.score, 2) for item in assessments})
        return assessments

    def _assess(self, dimension: FitDimension, evaluation: JevEvaluation) -> DimensionAssessment:
        result = evaluation.scores.get(dimension.value)
        if result is None:
            return DimensionAssessment(dimension=dimension, score=0.0, raw_score=0.0, level_label="not evaluated", confidence=0.0, low_confidence=True)
        return DimensionAssessment(
            dimension=dimension,
            score=result.normalized,
            raw_score=result.score,
            level_label=result.most_likely_level,
            confidence=result.confidence,
            low_confidence=self._is_low_confidence(result.confidence),
        )
