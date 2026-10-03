import logging
from pydantic import BaseModel
from app.core.exceptions import AnalysisInProgressError, InvalidJobInputError, MissingPrerequisiteError, TooManyJobsError
from app.domain.document_models import ParsedDocument
from app.domain.enums import AnalysisStatus, DocumentKind
from app.domain.job_models import JobInput, JobPosting
from app.domain.session_models import CandidatePreferences, Session
from app.repositories.session_repository import SessionLockRegistry, SessionRepository
from app.services.cv_export_service import CvExportService
from app.services.document_parser_service import DocumentParserService
from app.services.job_ingestion_service import JobIngestionService

logger = logging.getLogger(__name__)

class UploadedDocument(BaseModel):
    filename: str
    content: bytes

class DocumentSubmission(BaseModel):
    upload: UploadedDocument | None = None
    text: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.upload is None and not (self.text and self.text.strip())

class SessionService:
    def __init__(
        self,
        repository: SessionRepository,
        parser: DocumentParserService,
        ingestion: JobIngestionService,
        locks: SessionLockRegistry,
        export_service: CvExportService,
    ) -> None:
        self._repository = repository
        self._parser = parser
        self._ingestion = ingestion
        self._locks = locks
        self._export_service = export_service

    def create(self, preferences: CandidatePreferences | None) -> Session:
        session = Session(preferences=preferences or CandidatePreferences())
        self._repository.save(session)
        logger.info("session_created", extra={"session_id": session.id})
        return session

    def get(self, session_id: str) -> Session:
        return self._repository.get(session_id)

    def delete(self, session_id: str) -> None:
        self._repository.get(session_id)
        self._repository.delete(session_id)
        self._export_service.drop_session(session_id)
        self._locks.release(session_id)
        logger.info("session_deleted", extra={"session_id": session_id})

    async def update_preferences(self, session_id: str, preferences: CandidatePreferences) -> Session:
        async with self._locks.lock_for(session_id):
            session = self._editable(session_id)
            session.preferences = preferences
            self._repository.save(session)
            return session

    async def attach_documents(self, session_id: str, cv: DocumentSubmission, extra: DocumentSubmission) -> Session:
        if cv.is_empty and extra.is_empty:
            raise MissingPrerequisiteError("Upload or paste at least the CV.")
        parsed_cv = None if cv.is_empty else self._parse(cv, DocumentKind.CV)
        parsed_extra = None if extra.is_empty else self._parse(extra, DocumentKind.EXTRA)
        async with self._locks.lock_for(session_id):
            session = self._editable(session_id)
            session.cv = parsed_cv or session.cv
            session.extra_document = parsed_extra or session.extra_document
            if session.cv is None:
                raise MissingPrerequisiteError("The CV is required. Upload or paste it together with the extra document.")
            self._repository.save(session)
        logger.info("documents_attached", extra={"session_id": session_id, "cv_sections": len(session.cv.sections), "has_extra": session.extra_document is not None})
        return session

    async def add_jobs(self, session_id: str, inputs: list[JobInput]) -> list[JobPosting]:
        session = self._editable(session_id)
        if len(session.jobs) + len(inputs) > self._ingestion.max_jobs:
            raise TooManyJobsError(f"A session can hold at most {self._ingestion.max_jobs} jobs.")
        postings = await self._ingestion.ingest_many(inputs)
        async with self._locks.lock_for(session_id):
            session = self._editable(session_id)
            session.jobs.extend(postings)
            self._repository.save(session)
        return postings

    async def update_job_text(self, session_id: str, job_id: str, text: str) -> JobPosting:
        if not text.strip():
            raise InvalidJobInputError("Paste the job description text.")
        async with self._locks.lock_for(session_id):
            session = self._editable(session_id)
            updated = self._ingestion.replace_text(session.find_job(job_id), text)
            session.replace_job(updated)
            self._repository.save(session)
            return updated

    async def remove_job(self, session_id: str, job_id: str) -> Session:
        async with self._locks.lock_for(session_id):
            session = self._editable(session_id)
            session.find_job(job_id)
            session.jobs = [job for job in session.jobs if job.id != job_id]
            session.analysis.results.pop(job_id, None)
            self._repository.save(session)
            return session

    def _editable(self, session_id: str) -> Session:
        session = self._repository.get(session_id)
        if session.analysis.status == AnalysisStatus.RUNNING:
            raise AnalysisInProgressError("An analysis is running for this session. Wait until it finishes.")
        return session

    def _parse(self, submission: DocumentSubmission, kind: DocumentKind) -> ParsedDocument:
        if submission.upload is not None:
            return self._parser.parse_file(submission.upload.filename, submission.upload.content, kind)
        return self._parser.parse_text(submission.text or "", kind)
