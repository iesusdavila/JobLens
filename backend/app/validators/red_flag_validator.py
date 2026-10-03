import asyncio
from pydantic import BaseModel
from app.clients.jev_questions import NoulQuestion
from app.domain.enums import RiskSide
from app.domain.job_models import JobPosting, ParsedJob
from app.domain.profile_models import CandidateProfile
from app.domain.session_models import CandidatePreferences
from app.domain.validation_models import JevEvaluation, RedFlag
from app.validators.base_validator import BaseValidator

class RedFlagDefinition(BaseModel):
    code: str
    side: RiskSide
    question: str
    description: str
    severity: float
    requires_preferences: bool = False

class RedFlagValidator(BaseValidator):
    SCAM_CODE = "suspicious_posting"
    DEFINITIONS: list[RedFlagDefinition] = [
        RedFlagDefinition(code="vague_responsibilities", side=RiskSide.JOB, severity=0.3, question="Are the responsibilities in `job_posting` so vague that a candidate cannot tell what the daily work would be?", description="Responsibilities are vague."),
        RedFlagDefinition(code="unrealistic_requirements", side=RiskSide.JOB, severity=0.3, question="Does `job_posting` ask for an unrealistic combination of skills, years or roles for a single position?", description="The requirement stack looks unrealistic for one role."),
        RedFlagDefinition(code=SCAM_CODE, side=RiskSide.JOB, severity=1.0, question="Does `job_posting` show signs of a scam, such as upfront payments, requests for bank or ID data, or promises of easy money?", description="The posting shows scam-like signals."),
        RedFlagDefinition(code="location_conflict", side=RiskSide.JOB, severity=0.5, requires_preferences=True, question="Does the job location in `job_posting` conflict with the locations in `candidate_preferences`?", description="Job location conflicts with the candidate's preferred locations."),
        RedFlagDefinition(code="modality_conflict", side=RiskSide.JOB, severity=0.5, requires_preferences=True, question="Does the work modality (remote, hybrid or onsite) in `job_posting` conflict with `candidate_preferences`?", description="Work modality conflicts with the candidate's preference."),
        RedFlagDefinition(code="salary_conflict", side=RiskSide.JOB, severity=0.4, requires_preferences=True, question="Does `job_posting` state a salary that is clearly below the minimum in `candidate_preferences`?", description="Stated salary is below the candidate's minimum."),
        RedFlagDefinition(code="unexplained_gaps", side=RiskSide.CANDIDATE, severity=0.2, question="Does `candidate_timeline` contain an employment gap longer than one year that nothing in `candidate_profile` explains?", description="The candidate's timeline has unexplained gaps."),
        RedFlagDefinition(code="missing_must_haves", side=RiskSide.CANDIDATE, severity=0.5, question="Is at least one item of `must_have_requirements` completely absent from `candidate_profile`?", description="At least one must-have requirement is absent from the candidate's documents."),
    ]

    @property
    def name(self) -> str:
        return "red_flag"

    async def validate(
        self,
        job: JobPosting,
        parsed_job: ParsedJob,
        profile: CandidateProfile,
        preferences: CandidatePreferences,
    ) -> list[RedFlag]:
        job_definitions = self._job_definitions(preferences)
        candidate_definitions = [item for item in self.DEFINITIONS if item.side == RiskSide.CANDIDATE]
        job_evaluation, candidate_evaluation = await asyncio.gather(
            self._jev.evaluate(self._job_state(job, preferences), self._questions(job_definitions)),
            self._jev.evaluate(self._candidate_state(parsed_job, profile), self._questions(candidate_definitions)),
        )
        flags = [self._flag(item, job_evaluation) for item in job_definitions]
        flags += [self._flag(item, candidate_evaluation) for item in candidate_definitions]
        self._log_summary(evaluated=len(flags), triggered=[flag.code for flag in flags if flag.triggered])
        return flags

    def _job_definitions(self, preferences: CandidatePreferences) -> list[RedFlagDefinition]:
        return [
            item for item in self.DEFINITIONS
            if item.side == RiskSide.JOB and (not item.requires_preferences or not preferences.is_empty)
        ]

    def _questions(self, definitions: list[RedFlagDefinition]) -> list[NoulQuestion]:
        return [NoulQuestion(key=item.code, instructions=item.question) for item in definitions]

    def _job_state(self, job: JobPosting, preferences: CandidatePreferences) -> dict[str, object]:
        state: dict[str, object] = {"job_posting": job.text[: self._evidence_budget]}
        if not preferences.is_empty:
            state["candidate_preferences"] = preferences.model_dump(exclude_none=True)
        return state

    def _candidate_state(self, parsed_job: ParsedJob, profile: CandidateProfile) -> dict[str, object]:
        return {
            "must_have_requirements": parsed_job.must_have_requirements,
            "candidate_timeline": profile.timeline_state(),
            "candidate_profile": profile.compact_state(),
        }

    def _flag(self, definition: RedFlagDefinition, evaluation: JevEvaluation) -> RedFlag:
        result = evaluation.nouls.get(definition.code)
        probability = result.probability if result else 0.0
        return RedFlag(
            code=definition.code,
            side=definition.side,
            description=definition.description,
            probability=probability,
            severity=definition.severity,
            triggered=probability >= self._thresholds.red_flag_triggered,
        )
