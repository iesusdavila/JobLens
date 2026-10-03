from datetime import datetime
from pydantic import BaseModel, Field
from app.domain.cv_models import CvChange, TailoredCv
from app.domain.enums import AnalysisStatus, JobAnalysisStatus, Recommendation
from app.domain.job_models import ParsedJob
from app.domain.validation_models import CvValidationReport, FitAnalysis

class JobAnalysisResult(BaseModel):
    job_id: str
    status: JobAnalysisStatus
    job_name: str
    title: str | None = None
    company: str | None = None
    parsed_job: ParsedJob | None = None
    fit: FitAnalysis | None = None
    tailored_cv: TailoredCv | None = None
    changes: list[CvChange] = Field(default_factory=list)
    cv_validation: CvValidationReport | None = None
    markdown_preview: str | None = None
    change_log_markdown: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    iterations: int = 0

class RankingEntry(BaseModel):
    rank: int
    job_id: str
    job_name: str
    title: str | None
    company: str | None
    overall_score: float
    recommendation: Recommendation
    must_have_coverage: float | None
    ats_original: float
    ats_tailored: float | None

class AnalysisRun(BaseModel):
    status: AnalysisStatus = AnalysisStatus.IDLE
    job_statuses: dict[str, JobAnalysisStatus] = Field(default_factory=dict)
    results: dict[str, JobAnalysisResult] = Field(default_factory=dict)
    ranking: list[RankingEntry] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None

    @property
    def progress(self) -> float:
        if not self.job_statuses:
            return 0.0
        finished = {JobAnalysisStatus.COMPLETED, JobAnalysisStatus.COMPLETED_WITH_WARNINGS, JobAnalysisStatus.FAILED, JobAnalysisStatus.SKIPPED}
        done = sum(1 for status in self.job_statuses.values() if status in finished)
        return done / len(self.job_statuses)
