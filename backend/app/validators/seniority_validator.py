from app.clients.jev_questions import ChoiceQuestion, JevQuestion, NoulQuestion
from app.domain.enums import SeniorityMatch
from app.domain.job_models import ParsedJob
from app.domain.profile_models import CandidateProfile
from app.domain.validation_models import SeniorityAssessment
from app.validators.base_validator import BaseValidator

class SeniorityValidator(BaseValidator):
    LEVEL_KEY = "seniority_level"
    YEARS_KEY = "years_requirement"
    LEVEL_QUESTION = "Compared with the seniority `job` asks for, where does the experience in `candidate` place the candidate?"
    LEVEL_OPTIONS = {
        SeniorityMatch.BELOW.value: "The candidate's scope, years and responsibilities are clearly below what the job asks for.",
        SeniorityMatch.MATCHES.value: "The candidate's scope, years and responsibilities are about what the job asks for.",
        SeniorityMatch.ABOVE.value: "The candidate's scope, years and responsibilities are clearly above what the job asks for.",
    }
    YEARS_QUESTION = "Does `candidate` have at least `required_years` years of professional experience relevant to `job`?"

    @property
    def name(self) -> str:
        return "seniority"

    async def validate(self, parsed_job: ParsedJob, profile: CandidateProfile) -> SeniorityAssessment:
        state = {
            "job": {
                "title": parsed_job.title,
                "seniority_level": parsed_job.seniority_level,
                "min_years_experience": parsed_job.min_years_experience,
                "responsibilities": parsed_job.responsibilities[:8],
            },
            "candidate": {
                "headline": profile.headline,
                "total_years_experience": profile.total_years_experience,
                "experience_timeline": profile.timeline_state(),
            },
        }
        evaluation = await self._jev.evaluate(state, self._questions(parsed_job))
        level = evaluation.choices[self.LEVEL_KEY]
        years = evaluation.nouls.get(self.YEARS_KEY)
        assessment = SeniorityAssessment(
            match=SeniorityMatch(level.choice),
            probabilities=level.probabilities,
            confidence=level.confidence,
            years_required=parsed_job.min_years_experience,
            years_requirement_probability=years.probability if years else None,
            low_confidence=self._is_low_confidence(level.confidence),
        )
        self._log_summary(match=assessment.match.value, confidence=round(assessment.confidence, 2))
        return assessment

    def _questions(self, parsed_job: ParsedJob) -> list[JevQuestion]:
        questions: list[JevQuestion] = [ChoiceQuestion(key=self.LEVEL_KEY, instructions=self.LEVEL_QUESTION, options=self.LEVEL_OPTIONS)]
        if parsed_job.min_years_experience:
            questions.append(
                NoulQuestion(
                    key=self.YEARS_KEY,
                    instructions={"required_years": parsed_job.min_years_experience, "question": self.YEARS_QUESTION},
                )
            )
        return questions
