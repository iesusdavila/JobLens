import asyncio
import logging
from app.agents.analysis.analysis_agent import AnalysisAgent
from app.core.exceptions import AnalysisInProgressError, AnalysisNotReadyError, MissingPrerequisiteError, SessionNotFoundError
from app.domain.analysis_models import AnalysisRun, JobAnalysisResult, RankingEntry
from app.domain.enums import AnalysisStatus, JobAnalysisStatus
from app.domain.job_models import JobPosting
from app.domain.session_models import Session, utc_now
from app.repositories.session_repository import SessionLockRegistry, SessionRepository
from app.services.background_task_manager import BackgroundTaskManager

logger = logging.getLogger(__name__)

class RankingBuilder:
    def build(self, results: dict[str, JobAnalysisResult]) -> list[RankingEntry]:
        ranked = sorted(
            (result for result in results.values() if result.fit is not None),
            key=lambda result: (result.fit.overall_score, result.fit.must_have_coverage or 0.0),
            reverse=True,
        )
        return [self._entry(position, result) for position, result in enumerate(ranked, start=1)]

    @staticmethod
    def _entry(position: int, result: JobAnalysisResult) -> RankingEntry:
        return RankingEntry(
            rank=position,
            job_id=result.job_id,
            job_name=result.job_name,
            title=result.title,
            company=result.company,
            overall_score=result.fit.overall_score,
            recommendation=result.fit.recommendation,
            must_have_coverage=result.fit.must_have_coverage,
            ats_original=result.fit.ats_original.score,
            ats_tailored=result.cv_validation.ats_tailored.score if result.cv_validation else None,
        )

class AnalysisService:
    def __init__(
        self,
        repository: SessionRepository,
        agent: AnalysisAgent,
        ranking_builder: RankingBuilder,
        locks: SessionLockRegistry,
        task_manager: BackgroundTaskManager,
        max_concurrency: int,
    ) -> None:
        self._repository = repository
        self._agent = agent
        self._ranking_builder = ranking_builder
        self._locks = locks
        self._task_manager = task_manager
        self._max_concurrency = max_concurrency

    async def start(self, session_id: str, background: bool) -> AnalysisRun:
        async with self._locks.lock_for(session_id):
            session = self._repository.get(session_id)
            self._ensure_can_start(session)
            session.analysis = self._new_run(session)
            self._repository.save(session)
        logger.info("analysis_started", extra={"session_id": session_id, "jobs": len(session.jobs), "background": background})
        if background:
            self._task_manager.launch(self._execute(session_id))
            return session.analysis
        await self._execute(session_id)
        return self._repository.get(session_id).analysis

    def status(self, session_id: str) -> AnalysisRun:
        return self._repository.get(session_id).analysis

    def results(self, session_id: str) -> AnalysisRun:
        analysis = self.status(session_id)
        if analysis.status == AnalysisStatus.IDLE:
            raise AnalysisNotReadyError("No analysis has been started for this session.")
        return analysis

    def _ensure_can_start(self, session: Session) -> None:
        if session.analysis.status == AnalysisStatus.RUNNING:
            raise AnalysisInProgressError("An analysis is already running for this session.")
        if session.cv is None:
            raise MissingPrerequisiteError("Upload or paste the CV before running the analysis.")
        if not any(job.is_ready for job in session.jobs):
            raise MissingPrerequisiteError("Add at least one readable job. Paste the description for jobs whose URL could not be read.")

    @staticmethod
    def _new_run(session: Session) -> AnalysisRun:
        statuses = {job.id: JobAnalysisStatus.PENDING if job.is_ready else JobAnalysisStatus.SKIPPED for job in session.jobs}
        skipped = {
            job.id: JobAnalysisResult(job_id=job.id, status=JobAnalysisStatus.SKIPPED, job_name=job.display_name, error=job.message or "The job description is not available. Paste it to include this job.")
            for job in session.jobs if not job.is_ready
        }
        return AnalysisRun(status=AnalysisStatus.RUNNING, job_statuses=statuses, results=skipped, started_at=utc_now())

    async def _execute(self, session_id: str) -> None:
        try:
            session = self._repository.get(session_id)
            semaphore = asyncio.Semaphore(self._max_concurrency)
            await asyncio.gather(*(self._run_job(session, job, semaphore) for job in session.jobs if job.is_ready))
            await self._complete(session_id)
        except SessionNotFoundError:
            logger.warning("analysis_session_vanished", extra={"session_id": session_id})
        except Exception:
            logger.exception("analysis_run_crashed", extra={"session_id": session_id})
            await self._mark_failed(session_id)

    async def _mark_failed(self, session_id: str) -> None:
        async with self._locks.lock_for(session_id):
            session = self._repository.get(session_id)
            session.analysis.status = AnalysisStatus.FAILED
            session.analysis.finished_at = utc_now()
            session.analysis.error = "The analysis was interrupted by an unexpected error. Try again."
            self._repository.save(session)

    async def _run_job(self, session: Session, job: JobPosting, semaphore: asyncio.Semaphore) -> None:
        async with semaphore:
            await self._update(session.id, job.id, JobAnalysisStatus.RUNNING, None)
            try:
                result = await self._agent.run(session.id, job, session.cv, session.extra_document, session.preferences)
            except Exception:
                logger.exception("analysis_job_crashed", extra={"session_id": session.id, "job_id": job.id})
                result = JobAnalysisResult(job_id=job.id, status=JobAnalysisStatus.FAILED, job_name=job.display_name, error="An unexpected error interrupted this analysis. Try again.")
            await self._update(session.id, job.id, result.status, result)

    async def _update(self, session_id: str, job_id: str, status: JobAnalysisStatus, result: JobAnalysisResult | None) -> None:
        async with self._locks.lock_for(session_id):
            session = self._repository.get(session_id)
            session.analysis.job_statuses[job_id] = status
            if result is not None:
                session.analysis.results[job_id] = result
            self._repository.save(session)

    async def _complete(self, session_id: str) -> None:
        async with self._locks.lock_for(session_id):
            session = self._repository.get(session_id)
            analysis = session.analysis
            analysis.ranking = self._ranking_builder.build(analysis.results)
            analysis.finished_at = utc_now()
            succeeded = any(result.fit is not None for result in analysis.results.values())
            analysis.status = AnalysisStatus.COMPLETED if succeeded else AnalysisStatus.FAILED
            analysis.error = None if succeeded else "No job could be analyzed. Check the per-job errors."
            self._repository.save(session)
        logger.info("analysis_completed", extra={"session_id": session_id, "status": analysis.status.value, "ranked": len(analysis.ranking)})
