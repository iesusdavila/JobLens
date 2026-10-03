import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, StructuredTool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from app.agents.analysis.agent_state import AnalysisAgentState, ScoredDraft
from app.agents.analysis.finalizer import AnalysisFinalizer
from app.agents.analysis.stop_policy import AgentStopPolicy, NextStepAdvisor
from app.core.exceptions import AppError
from app.domain.enums import AgentStatus
from app.domain.validation_models import CvValidationReport
from app.services.cv_evaluation_service import CvEvaluationService
from app.services.cv_tailoring_service import CvTailoringService, TailoringContext
from app.services.fit_evaluation_service import FitEvaluationService
from app.services.job_requirement_extraction_service import JobRequirementExtractionService
from app.services.profile_extraction_service import ProfileExtractionService

logger = logging.getLogger(__name__)
ToolOutcome = tuple[str, dict[str, Any]]

class ToolFeedbackFormatter:
    def feedback(self, report: CvValidationReport) -> list[str]:
        items = [f"Unsupported claim, remove it or rewrite it strictly from the sources: {check.text}" for check in report.unsupported_claims]
        if not report.ats_improved:
            items.append(
                "ATS alignment did not improve over the original CV. Surface the strongest relevant evidence earlier and mirror these job terms ONLY where the sources prove the candidate has them: "
                + ", ".join(report.ats_tailored.missing_keywords or ["(no specific terms)"])
            )
        items.extend(f"Quality issue ({check.name}): {check.detail}" for check in report.quality.failing_checks())
        return items

    def validation_summary(self, report: CvValidationReport) -> str:
        return (
            f"Claims checked: {len(report.claim_checks)}, unsupported: {len(report.unsupported_claims)}.\n"
            f"ATS alignment: original {report.ats_original.score:.2f}, tailored {report.ats_tailored.score:.2f}, improved: {report.ats_improved}.\n"
            f"Quality checks passed: {sum(1 for check in report.quality.checks if check.passed)}/{len(report.quality.checks)}."
        )

class AnalysisToolkit:
    def __init__(
        self,
        job_extractor: JobRequirementExtractionService,
        profile_extractor: ProfileExtractionService,
        fit_service: FitEvaluationService,
        tailoring_service: CvTailoringService,
        cv_evaluation_service: CvEvaluationService,
        finalizer: AnalysisFinalizer,
        stop_policy: AgentStopPolicy,
        advisor: NextStepAdvisor,
        formatter: ToolFeedbackFormatter,
    ) -> None:
        self._job_extractor = job_extractor
        self._profile_extractor = profile_extractor
        self._fit_service = fit_service
        self._tailoring_service = tailoring_service
        self._cv_evaluation_service = cv_evaluation_service
        self._finalizer = finalizer
        self._stop_policy = stop_policy
        self._advisor = advisor
        self._formatter = formatter

    def tools(self) -> list[BaseTool]:
        return [
            StructuredTool.from_function(coroutine=self.extract_job_requirements, name="extract_job_requirements", description="Extract the structured requirements of the job posting."),
            StructuredTool.from_function(coroutine=self.parse_candidate_profile, name="parse_candidate_profile", description="Parse the CV and the optional extra document into a traceable candidate profile."),
            StructuredTool.from_function(coroutine=self.run_fit_validation, name="run_fit_validation", description="Run the Jev fit validators and compute the fit score and recommendation."),
            StructuredTool.from_function(coroutine=self.draft_tailored_cv, name="draft_tailored_cv", description="Write a tailored CV draft from real evidence only. Optional revision_focus summarizes what the new draft must fix."),
            StructuredTool.from_function(coroutine=self.run_cv_validation, name="run_cv_validation", description="Validate the current draft: claim faithfulness, ATS alignment and quality."),
            StructuredTool.from_function(coroutine=self.finalize_outputs, name="finalize_outputs", description="Render DOCX, PDF and Markdown and store the analysis. Ends the work."),
        ]

    async def extract_job_requirements(self, state: Annotated[dict, InjectedState], tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        return await self._run("extract_job_requirements", state, tool_call_id, self._extract_job)

    async def parse_candidate_profile(self, state: Annotated[dict, InjectedState], tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        return await self._run("parse_candidate_profile", state, tool_call_id, self._parse_profile)

    async def run_fit_validation(self, state: Annotated[dict, InjectedState], tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        return await self._run("run_fit_validation", state, tool_call_id, self._validate_fit)

    async def draft_tailored_cv(self, state: Annotated[dict, InjectedState], tool_call_id: Annotated[str, InjectedToolCallId], revision_focus: str = "") -> Command:
        async def operation(current: AnalysisAgentState) -> ToolOutcome:
            return await self._draft(current, revision_focus)
        return await self._run("draft_tailored_cv", state, tool_call_id, operation)

    async def run_cv_validation(self, state: Annotated[dict, InjectedState], tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        return await self._run("run_cv_validation", state, tool_call_id, self._validate_cv)

    async def finalize_outputs(self, state: Annotated[dict, InjectedState], tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
        return await self._run("finalize_outputs", state, tool_call_id, self._finalize)

    async def _run(self, name: str, state: AnalysisAgentState, tool_call_id: str, operation: Callable[[AnalysisAgentState], Awaitable[ToolOutcome]]) -> Command:
        started = time.perf_counter()
        try:
            content, update = await operation(state)
        except AppError as error:
            return self._failure(name, state, tool_call_id, error)
        except Exception as error:
            logger.exception("agent_tool_crashed", extra={"tool": name, "job_id": state["job"].id})
            return self._failure(name, state, tool_call_id, AppError(f"Unexpected internal error ({type(error).__name__}) in {name}."))
        logger.info("agent_tool_completed", extra={"tool": name, "job_id": state["job"].id, "iteration": update.get("iteration", state.get("iteration", 0)), "elapsed_ms": round((time.perf_counter() - started) * 1000)})
        return Command(update={"last_error": None, **update, "messages": [ToolMessage(content=content, tool_call_id=tool_call_id, name=name)]})

    def _failure(self, name: str, state: AnalysisAgentState, tool_call_id: str, error: AppError) -> Command:
        tool_errors = state.get("tool_errors", 0) + 1
        logger.warning("agent_tool_failed", extra={"tool": name, "job_id": state["job"].id, "error_code": error.error_code, "tool_errors": tool_errors})
        update: dict[str, Any] = {"tool_errors": tool_errors, "last_error": error.message}
        content = f"STATUS: ERROR\nTool {name} failed: {error.message}"
        if self._stop_policy.tool_errors_exhausted(tool_errors):
            merged: AnalysisAgentState = {**state, **update}
            update["result"] = self._finalizer.finalize(merged, forced=True, reason=f"Stopped after {tool_errors} tool errors. Last error: {error.message}")
            update["status"] = AgentStatus.FINALIZED
            content += "\nToo many errors. The analysis was finalized with the available results."
        return Command(update={**update, "messages": [ToolMessage(content=content, tool_call_id=tool_call_id, name=name, status="error")]})

    def _missing(self, state: AnalysisAgentState) -> ToolOutcome:
        return f"STATUS: MISSING_PREREQUISITE\nCall {self._advisor.suggest(state)} first.", {}

    async def _extract_job(self, state: AnalysisAgentState) -> ToolOutcome:
        parsed = await self._job_extractor.extract(state["job"])
        content = (
            f"STATUS: OK\nTitle: {parsed.title}\nCompany: {parsed.company or 'not stated'}\n"
            f"Must-have requirements: {len(parsed.must_have_requirements)}\nNice-to-have requirements: {len(parsed.nice_to_have_requirements)}\n"
            f"Keywords: {', '.join(parsed.keywords)}"
        )
        return content, {"parsed_job": parsed, "requirements": parsed.requirements()}

    async def _parse_profile(self, state: AnalysisAgentState) -> ToolOutcome:
        profile = await self._profile_extractor.extract(state["cv_document"], state.get("extra_document"))
        content = (
            f"STATUS: OK\nExperiences: {len(profile.experiences)}, skills: {len(profile.skills)}, projects: {len(profile.projects)}, "
            f"education entries: {len(profile.education)}, certifications: {len(profile.certifications)}."
        )
        return content, {"profile": profile}

    async def _validate_fit(self, state: AnalysisAgentState) -> ToolOutcome:
        if state.get("parsed_job") is None or state.get("profile") is None:
            return self._missing(state)
        fit = await self._fit_service.evaluate(
            state["job"], state["parsed_job"], state["profile"], state["cv_document"], state.get("extra_document"), state["preferences"]
        )
        content = (
            f"STATUS: OK\nOverall fit: {fit.overall_score}/100\nRecommendation: {fit.recommendation.value}\n"
            f"Must-have coverage: {fit.must_have_coverage if fit.must_have_coverage is not None else 'n/a'}\n"
            f"ATS alignment of the original CV: {fit.ats_original.score:.2f}\nGaps: {len(fit.gaps)}\nNext: draft_tailored_cv"
        )
        return content, {"fit_analysis": fit}

    async def _draft(self, state: AnalysisAgentState, revision_focus: str) -> ToolOutcome:
        if state.get("fit_analysis") is None:
            return self._missing(state)
        iteration = state.get("iteration", 0)
        if self._stop_policy.iteration_cap_reached(iteration):
            return f"STATUS: ITERATION_CAP_REACHED\n{iteration} drafts were produced. Call finalize_outputs.", {}
        context = TailoringContext(
            parsed_job=state["parsed_job"],
            profile=state["profile"],
            cv_text=state["cv_document"].text,
            extra_text=state["extra_document"].text if state.get("extra_document") else None,
            gaps=state["fit_analysis"].missing_requirement_texts(),
            feedback=state.get("last_feedback", []),
            revision_focus=revision_focus or None,
            previous_draft=state.get("draft"),
        )
        result = await self._tailoring_service.draft(context)
        corrections = "\n".join(f"- {item}" for item in result.corrections) or "- none"
        content = f"STATUS: OK\nDraft {iteration + 1} created with {len(result.draft.changes)} recorded changes.\nFact guard corrections:\n{corrections}\nNext: run_cv_validation"
        return content, {"draft": result.draft, "cv_validation": None, "iteration": iteration + 1}

    async def _validate_cv(self, state: AnalysisAgentState) -> ToolOutcome:
        if state.get("draft") is None:
            return self._missing(state)
        sources = state["cv_document"].sections + (state["extra_document"].sections if state.get("extra_document") else [])
        report = await self._cv_evaluation_service.evaluate(state["parsed_job"], state["draft"], sources, state["fit_analysis"].ats_original)
        iteration = state.get("iteration", 0)
        best = self._stop_policy.best_of(state.get("best_attempt"), ScoredDraft(draft=state["draft"], report=report, iteration=iteration))
        feedback = self._formatter.feedback(report)
        update = {"cv_validation": report, "best_attempt": best, "last_feedback": feedback}
        summary = self._formatter.validation_summary(report)
        if report.ready_to_finalize:
            return f"STATUS: READY_TO_FINALIZE\n{summary}\nNext: finalize_outputs", update
        failing = "\n".join(f"- {item}" for item in feedback)
        if self._stop_policy.iteration_cap_reached(iteration):
            return f"STATUS: ITERATION_CAP_REACHED\n{summary}\nUnresolved:\n{failing}\nNext: finalize_outputs", update
        return f"STATUS: NEEDS_REVISION\n{summary}\nFailing items:\n{failing}\nNext: draft_tailored_cv with a revision_focus", update

    async def _finalize(self, state: AnalysisAgentState) -> ToolOutcome:
        if not self._stop_policy.may_finalize(state):
            next_step = self._advisor.suggest(state)
            return (
                f"STATUS: REFUSED\nValidation is not passing yet and only {state.get('iteration', 0)} of {self._stop_policy.max_iterations} iterations were used. Call {next_step}.",
                {},
            )
        result = self._finalizer.finalize(state, forced=False)
        return f"STATUS: DONE\nAnalysis stored with status {result.status.value}.", {"result": result, "status": AgentStatus.FINALIZED}
