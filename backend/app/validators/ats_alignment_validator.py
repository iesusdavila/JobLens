from app.clients.jev_questions import JevQuestion, NoulQuestion, ScoreQuestion
from app.domain.job_models import ParsedJob
from app.domain.validation_models import AtsAlignment, JevEvaluation
from app.validators.base_validator import BaseValidator

class AtsAlignmentValidator(BaseValidator):
    KEYWORD_WEIGHT = 0.5
    MIRRORING_WEIGHT = 0.25
    PRIORITY_WEIGHT = 0.25
    MIRRORING_KEY = "terminology_mirroring"
    PRIORITY_KEY = "priority_alignment"
    TERM_QUESTION = "Does `cv` explicitly mention `term`, or a standard synonym or abbreviation of it?"
    MIRRORING_QUESTION = "How closely does the wording of `cv` mirror the terminology used in `job_key_terms`?"
    MIRRORING_LEVELS = [
        "Uses none of the job's terms",
        "Uses a few of the job's terms",
        "Uses about half of the job's terms",
        "Uses most of the job's terms naturally",
        "Uses nearly all of the job's terms naturally",
    ]
    PRIORITY_QUESTION = "How prominently does `cv` place evidence for `job_priorities`, in its summary, skills and first bullets?"
    PRIORITY_LEVELS = [
        "Evidence for the priorities is absent or buried at the end",
        "Evidence appears but is hard to find",
        "Evidence is visible in some prominent places",
        "Evidence is prominent for most priorities",
        "Evidence for every priority is in the most prominent places",
    ]

    @property
    def name(self) -> str:
        return "ats_alignment"

    async def validate(self, parsed_job: ParsedJob, cv_text: str) -> AtsAlignment:
        terms = parsed_job.key_terms()[:20]
        state = {
            "job_priorities": parsed_job.must_have_requirements[:8],
            "job_key_terms": terms,
            "cv": cv_text[: self._evidence_budget],
        }
        evaluation = await self._jev.evaluate(state, self._questions(terms))
        alignment = self._combine(terms, evaluation)
        self._log_summary(score=round(alignment.score, 3), terms=len(terms), missing=len(alignment.missing_keywords))
        return alignment

    def _questions(self, terms: list[str]) -> list[JevQuestion]:
        questions: list[JevQuestion] = [
            NoulQuestion(key=self._term_key(index), instructions={"term": term, "question": self.TERM_QUESTION})
            for index, term in enumerate(terms)
        ]
        questions.append(ScoreQuestion(key=self.MIRRORING_KEY, instructions=self.MIRRORING_QUESTION, levels=self.MIRRORING_LEVELS))
        questions.append(ScoreQuestion(key=self.PRIORITY_KEY, instructions=self.PRIORITY_QUESTION, levels=self.PRIORITY_LEVELS))
        return questions

    def _combine(self, terms: list[str], evaluation: JevEvaluation) -> AtsAlignment:
        matched = [term for index, term in enumerate(terms) if self._term_probability(index, evaluation) >= self._thresholds.keyword_present]
        missing = [term for term in terms if term not in matched]
        coverage = len(matched) / len(terms) if terms else 0.0
        mirroring = evaluation.scores[self.MIRRORING_KEY]
        priority = evaluation.scores[self.PRIORITY_KEY]
        score = self.KEYWORD_WEIGHT * coverage + self.MIRRORING_WEIGHT * mirroring.normalized + self.PRIORITY_WEIGHT * priority.normalized
        return AtsAlignment(
            score=round(score, 4),
            keyword_coverage=coverage,
            terminology_mirroring=mirroring.normalized,
            priority_alignment=priority.normalized,
            confidence=(mirroring.confidence + priority.confidence) / 2,
            matched_keywords=matched,
            missing_keywords=missing,
        )

    def _term_probability(self, index: int, evaluation: JevEvaluation) -> float:
        result = evaluation.nouls.get(self._term_key(index))
        return result.probability if result else 0.0

    @staticmethod
    def _term_key(index: int) -> str:
        return f"term_{index}"
