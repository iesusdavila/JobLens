from app.clients.jev_client import JevClient
from app.clients.jev_questions import JevQuestion, NoulQuestion, ScoreQuestion
from app.config.settings import ValidationThresholds
from app.domain.cv_models import TailoredCv
from app.domain.job_models import ParsedJob
from app.domain.validation_models import CvQualityReport, JevEvaluation, QualityCheck
from app.validators.base_validator import BaseValidator

class CvQualityValidator(BaseValidator):
    ORDERING_KEY = "relevance_ordering"
    FILLER_KEY = "filler_present"
    CLARITY_KEY = "clarity"
    ORDERING_QUESTION = "Within each section of `cv`, are the items most relevant to `job` placed before the less relevant ones?"
    FILLER_QUESTION = "Does `cv` contain filler, such as generic buzzwords or self-praise with no concrete evidence behind it?"
    CLARITY_QUESTION = "How clear and specific are the bullets in `cv`?"
    CLARITY_LEVELS = [
        "Confusing or generic bullets",
        "Mostly generic bullets with few specifics",
        "Mixed: some specific, some generic",
        "Mostly specific, action-oriented bullets",
        "Consistently specific, concise, action-oriented bullets",
    ]

    def __init__(self, jev_client: JevClient, thresholds: ValidationThresholds, max_words: int, max_bullets_per_role: int) -> None:
        super().__init__(jev_client, thresholds)
        self._max_words = max_words
        self._max_bullets_per_role = max_bullets_per_role

    @property
    def name(self) -> str:
        return "cv_quality"

    async def validate(self, parsed_job: ParsedJob, cv: TailoredCv, cv_markdown: str) -> CvQualityReport:
        state = {"job": parsed_job.summary_state(), "cv": cv_markdown[: self._evidence_budget]}
        evaluation = await self._jev.evaluate(state, self._questions())
        checks = [
            self._ordering_check(evaluation),
            self._filler_check(evaluation),
            self._clarity_check(evaluation),
            self._length_check(cv_markdown),
            self._bullet_count_check(cv),
        ]
        report = CvQualityReport(checks=checks)
        self._log_summary(passed=report.passed, failing=[check.name for check in report.failing_checks()])
        return report

    def _questions(self) -> list[JevQuestion]:
        return [
            NoulQuestion(key=self.ORDERING_KEY, instructions=self.ORDERING_QUESTION),
            NoulQuestion(key=self.FILLER_KEY, instructions=self.FILLER_QUESTION),
            ScoreQuestion(key=self.CLARITY_KEY, instructions=self.CLARITY_QUESTION, levels=self.CLARITY_LEVELS),
        ]

    def _ordering_check(self, evaluation: JevEvaluation) -> QualityCheck:
        probability = evaluation.nouls[self.ORDERING_KEY].probability
        return QualityCheck(
            name=self.ORDERING_KEY,
            passed=probability >= self._thresholds.quality_noul_pass,
            value=probability,
            detail="Most relevant evidence should come first in each section.",
        )

    def _filler_check(self, evaluation: JevEvaluation) -> QualityCheck:
        probability = evaluation.nouls[self.FILLER_KEY].probability
        return QualityCheck(
            name="no_filler",
            passed=probability <= 1 - self._thresholds.quality_noul_pass,
            value=1 - probability,
            detail="Remove buzzwords and claims without concrete evidence.",
        )

    def _clarity_check(self, evaluation: JevEvaluation) -> QualityCheck:
        result = evaluation.scores[self.CLARITY_KEY]
        return QualityCheck(
            name=self.CLARITY_KEY,
            passed=result.normalized >= self._thresholds.quality_score_pass,
            value=result.normalized,
            detail=f"Bullets judged as: {result.most_likely_level}.",
        )

    def _length_check(self, cv_markdown: str) -> QualityCheck:
        words = len(cv_markdown.split())
        return QualityCheck(
            name="length",
            passed=words <= self._max_words,
            value=float(words),
            detail=f"{words} words, limit {self._max_words}.",
        )

    def _bullet_count_check(self, cv: TailoredCv) -> QualityCheck:
        largest = max((len(item.bullets) for item in cv.experiences), default=0)
        return QualityCheck(
            name="bullets_per_role",
            passed=largest <= self._max_bullets_per_role,
            value=float(largest),
            detail=f"Largest role has {largest} bullets, limit {self._max_bullets_per_role}.",
        )
