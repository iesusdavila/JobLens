from app.agents.analysis.agent_state import AnalysisAgentState, ScoredDraft
from app.domain.validation_models import CvValidationReport

class AgentStopPolicy:
    def __init__(self, max_iterations: int, max_steps: int, max_tool_errors: int, max_nudges: int) -> None:
        self._max_iterations = max_iterations
        self._max_steps = max_steps
        self._max_tool_errors = max_tool_errors
        self._max_nudges = max_nudges

    @property
    def max_iterations(self) -> int:
        return self._max_iterations

    def validation_passed(self, report: CvValidationReport | None) -> bool:
        return report is not None and report.ready_to_finalize

    def iteration_cap_reached(self, iteration: int) -> bool:
        return iteration >= self._max_iterations

    def steps_exhausted(self, agent_steps: int) -> bool:
        return agent_steps >= self._max_steps

    def nudges_exhausted(self, nudges: int) -> bool:
        return nudges >= self._max_nudges

    def tool_errors_exhausted(self, tool_errors: int) -> bool:
        return tool_errors >= self._max_tool_errors

    def may_finalize(self, state: AnalysisAgentState) -> bool:
        if state.get("fit_analysis") is None:
            return state.get("last_error") is not None
        return (
            self.validation_passed(state.get("cv_validation"))
            or self.iteration_cap_reached(state.get("iteration", 0))
            or state.get("last_error") is not None
        )

    def best_of(self, current: ScoredDraft | None, candidate: ScoredDraft) -> ScoredDraft:
        if current is None:
            return candidate
        return candidate if self._rank(candidate) >= self._rank(current) else current

    @staticmethod
    def _rank(attempt: ScoredDraft) -> tuple[bool, bool, int, float, int]:
        report = attempt.report
        passed_checks = sum(1 for check in report.quality.checks if check.passed)
        return (report.faithfulness_passed, report.ats_improved, -len(report.unsupported_claims), report.ats_tailored.score, passed_checks)

class NextStepAdvisor:
    def __init__(self, stop_policy: AgentStopPolicy) -> None:
        self._stop_policy = stop_policy

    def suggest(self, state: AnalysisAgentState) -> str:
        if state.get("parsed_job") is None:
            return "extract_job_requirements"
        if state.get("profile") is None:
            return "parse_candidate_profile"
        if state.get("fit_analysis") is None:
            return "run_fit_validation"
        if state.get("draft") is None:
            return "draft_tailored_cv"
        if state.get("cv_validation") is None:
            return "run_cv_validation"
        if self._stop_policy.may_finalize(state):
            return "finalize_outputs"
        return "draft_tailored_cv"
