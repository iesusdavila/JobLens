from datetime import datetime
from pydantic import BaseModel, Field
from app.domain.enums import AnalysisStatus, DocumentKind, IngestionStatus, JobSourceType
from app.domain.job_models import JobInput, JobPosting
from app.domain.document_models import ParsedDocument
from app.domain.session_models import CandidatePreferences, Session

class CreateSessionRequest(BaseModel):
    preferences: CandidatePreferences | None = None

class DocumentSummary(BaseModel):
    kind: DocumentKind
    filename: str
    word_count: int
    sections: list[str]

class JobSummary(BaseModel):
    id: str
    source_type: JobSourceType
    url: str | None
    label: str | None
    display_name: str
    ingestion_status: IngestionStatus
    message: str | None
    text_preview: str
    needs_manual_paste: bool

    @classmethod
    def from_posting(cls, posting: JobPosting) -> "JobSummary":
        return cls(
            id=posting.id,
            source_type=posting.source_type,
            url=posting.url,
            label=posting.label,
            display_name=posting.display_name,
            ingestion_status=posting.ingestion_status,
            message=posting.message,
            text_preview=posting.text[:400],
            needs_manual_paste=not posting.is_ready,
        )

class SessionResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    expires_in_minutes: int
    cv: DocumentSummary | None
    extra_document: DocumentSummary | None
    jobs: list[JobSummary]
    preferences: CandidatePreferences
    analysis_status: AnalysisStatus

    @classmethod
    def from_session(cls, session: Session, ttl_minutes: int) -> "SessionResponse":
        return cls(
            id=session.id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            expires_in_minutes=ttl_minutes,
            cv=cls._document(session.cv),
            extra_document=cls._document(session.extra_document),
            jobs=[JobSummary.from_posting(job) for job in session.jobs],
            preferences=session.preferences,
            analysis_status=session.analysis.status,
        )

    @staticmethod
    def _document(document: ParsedDocument | None) -> DocumentSummary | None:
        if document is None:
            return None
        return DocumentSummary(kind=document.kind, filename=document.filename, word_count=document.word_count, sections=[section.heading for section in document.sections])

class AddJobsRequest(BaseModel):
    jobs: list[JobInput] = Field(min_length=1)

class AddJobsResponse(BaseModel):
    jobs: list[JobSummary]
    needs_manual_paste: list[str]

class UpdateJobTextRequest(BaseModel):
    text: str = Field(min_length=1)
