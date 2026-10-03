from datetime import datetime
from pydantic import BaseModel
from app.domain.analysis_models import AnalysisRun, JobAnalysisResult, RankingEntry
from app.domain.enums import AnalysisStatus, JobAnalysisStatus

class AnalysisStatusResponse(BaseModel):
    status: AnalysisStatus
    progress: float
    job_statuses: dict[str, JobAnalysisStatus]
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None

    @classmethod
    def from_run(cls, run: AnalysisRun) -> "AnalysisStatusResponse":
        return cls(status=run.status, progress=run.progress, job_statuses=run.job_statuses, started_at=run.started_at, finished_at=run.finished_at, error=run.error)

class AnalysisResultsResponse(BaseModel):
    status: AnalysisStatus
    progress: float
    results: list[JobAnalysisResult]
    ranking: list[RankingEntry]
    error: str | None

    @classmethod
    def from_run(cls, run: AnalysisRun) -> "AnalysisResultsResponse":
        return cls(status=run.status, progress=run.progress, results=list(run.results.values()), ranking=run.ranking, error=run.error)
