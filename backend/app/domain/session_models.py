from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pydantic import BaseModel, Field
from app.core.exceptions import JobNotFoundError
from app.domain.analysis_models import AnalysisRun
from app.domain.document_models import ParsedDocument
from app.domain.enums import ChatRole
from app.domain.job_models import JobPosting

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class CandidatePreferences(BaseModel):
    desired_locations: list[str] = Field(default_factory=list)
    preferred_modality: str | None = None
    minimum_salary: str | None = None
    notes: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.desired_locations or self.preferred_modality or self.minimum_salary or self.notes)

class ChatMessage(BaseModel):
    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    sources: list[str] = Field(default_factory=list)

class Session(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    cv: ParsedDocument | None = None
    extra_document: ParsedDocument | None = None
    jobs: list[JobPosting] = Field(default_factory=list)
    preferences: CandidatePreferences = Field(default_factory=CandidatePreferences)
    analysis: AnalysisRun = Field(default_factory=AnalysisRun)
    chat_histories: dict[str, list[ChatMessage]] = Field(default_factory=dict)

    def find_job(self, job_id: str) -> JobPosting:
        for job in self.jobs:
            if job.id == job_id:
                return job
        raise JobNotFoundError(f"Job '{job_id}' does not exist in this session.")

    def replace_job(self, updated: JobPosting) -> None:
        self.jobs = [updated if job.id == updated.id else job for job in self.jobs]

    def touch(self) -> None:
        self.updated_at = utc_now()

    def is_expired(self, ttl: timedelta, now: datetime) -> bool:
        return now - self.updated_at > ttl
