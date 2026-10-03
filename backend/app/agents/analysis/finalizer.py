import logging
from app.agents.analysis.agent_state import AnalysisAgentState, ScoredDraft
from app.domain.analysis_models import JobAnalysisResult
from app.domain.cv_models import TailoredCv, TailoredCvDraft
from app.domain.enums import JobAnalysisStatus
from app.domain.validation_models import CvValidationReport
from app.services.cv_claims import CvClaimExtractor, CvClaimPruner
from app.services.cv_export_service import CvExportService
from app.services.cv_templates.markdown_renderer import ChangeLogRenderer

logger = logging.getLogger(__name__)

class AnalysisFinalizer:
    def __init__(
        self,
        export_service: CvExportService,
        claim_extractor: CvClaimExtractor,
        claim_pruner: CvClaimPruner,
        change_log_renderer: ChangeLogRenderer,
        max_iterations: int,
    ) -> None:
        self._export_service = export_service
        self._claim_extractor = claim_extractor
        self._claim_pruner = claim_pruner
        self._change_log_renderer = change_log_renderer
        self._max_iterations = max_iterations

    def finalize(self, state: AnalysisAgentState, forced: bool, reason: str | None = None) -> JobAnalysisResult:
        job = state["job"]
        parsed_job = state.get("parsed_job")
        base = JobAnalysisResult(
            job_id=job.id,
            status=JobAnalysisStatus.FAILED,
            job_name=job.display_name,
            title=parsed_job.title if parsed_job else None,
            company=parsed_job.company if parsed_job else None,
            parsed_job=parsed_job,
            fit=state.get("fit_analysis"),
            iterations=state.get("iteration", 0),
            warnings=list(state.get("warnings", [])),
        )
        if base.fit is None:
            base.error = state.get("last_error") or reason or "The analysis could not complete the fit validation."
            logger.warning("analysis_failed", extra={"job_id": job.id, "forced": forced})
            return base
        result = self._with_cv(base, state, forced, reason)
        result.status = JobAnalysisStatus.COMPLETED_WITH_WARNINGS if result.warnings else JobAnalysisStatus.COMPLETED
        logger.info("analysis_finalized", extra={"job_id": job.id, "status": result.status.value, "iterations": result.iterations, "forced": forced})
        return result

    def _with_cv(self, result: JobAnalysisResult, state: AnalysisAgentState, forced: bool, reason: str | None) -> JobAnalysisResult:
        draft, report = self._select(state)
        if forced and reason:
            result.warnings.append(reason)
        if draft is None:
            result.warnings.append(f"A tailored CV could not be produced: {state.get('last_error') or 'no draft was generated'}.")
            return result
        cv = draft.cv
        if report is None:
            result.warnings.append("The final draft could not be validated by Jev. Review every line before using it.")
        elif not report.ready_to_finalize:
            cv = self._prune_unsupported(draft, report, result)
        result.tailored_cv = cv
        result.changes = draft.changes
        result.cv_validation = report
        result.markdown_preview = self._export_service.render_and_store(state["session_id"], state["job"].id, cv)
        result.change_log_markdown = self._change_log_renderer.render(draft.changes)
        return result

    def _prune_unsupported(self, draft: TailoredCvDraft, report: CvValidationReport, result: JobAnalysisResult) -> TailoredCv:
        result.warnings.append(
            f"Validation did not fully pass after {result.iterations} of {self._max_iterations} iterations. Unresolved issues: "
            + "; ".join(report.unresolved_issues())
        )
        unsupported = {check.claim_id for check in report.unsupported_claims}
        if not unsupported:
            return draft.cv
        result.warnings.append(f"{len(unsupported)} unsupported claims were removed from the final CV to keep it truthful.")
        return self._claim_pruner.prune(draft.cv, self._claim_extractor.extract(draft.cv), unsupported)

    @staticmethod
    def _select(state: AnalysisAgentState) -> tuple[TailoredCvDraft | None, CvValidationReport | None]:
        current_report = state.get("cv_validation")
        draft = state.get("draft")
        if draft is not None and current_report is not None and current_report.ready_to_finalize:
            return draft, current_report
        best: ScoredDraft | None = state.get("best_attempt")
        if best is not None:
            return best.draft, best.report
        return draft, current_report
