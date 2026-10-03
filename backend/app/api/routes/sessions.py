from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from app.api.dependencies import get_session_service, get_settings
from app.api.schemas.session_schemas import AddJobsRequest, AddJobsResponse, CreateSessionRequest, JobSummary, SessionResponse, UpdateJobTextRequest
from app.config.settings import Settings
from app.core.exceptions import FileTooLargeError
from app.domain.session_models import CandidatePreferences
from app.services.session_service import DocumentSubmission, SessionService, UploadedDocument

router = APIRouter(prefix="/sessions", tags=["sessions"])

async def read_upload(upload: UploadFile | None, max_bytes: int) -> UploadedDocument | None:
    if upload is None or not upload.filename:
        return None
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise FileTooLargeError(f"'{upload.filename}' exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    return UploadedDocument(filename=upload.filename, content=content)

@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest | None = None,
    service: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    session = service.create(request.preferences if request else None)
    return SessionResponse.from_session(session, settings.session_ttl_minutes)

@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, service: SessionService = Depends(get_session_service), settings: Settings = Depends(get_settings)) -> SessionResponse:
    return SessionResponse.from_session(service.get(session_id), settings.session_ttl_minutes)

@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, service: SessionService = Depends(get_session_service)) -> None:
    service.delete(session_id)

@router.put("/{session_id}/preferences", response_model=SessionResponse)
async def update_preferences(
    session_id: str,
    preferences: CandidatePreferences,
    service: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    session = await service.update_preferences(session_id, preferences)
    return SessionResponse.from_session(session, settings.session_ttl_minutes)

@router.post("/{session_id}/documents", response_model=SessionResponse)
async def upload_documents(
    session_id: str,
    cv_file: UploadFile | None = File(default=None),
    cv_text: str | None = Form(default=None),
    extra_file: UploadFile | None = File(default=None),
    extra_text: str | None = Form(default=None),
    service: SessionService = Depends(get_session_service),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    cv = DocumentSubmission(upload=await read_upload(cv_file, settings.max_upload_bytes), text=cv_text)
    extra = DocumentSubmission(upload=await read_upload(extra_file, settings.max_upload_bytes), text=extra_text)
    session = await service.attach_documents(session_id, cv, extra)
    return SessionResponse.from_session(session, settings.session_ttl_minutes)

@router.post("/{session_id}/jobs", response_model=AddJobsResponse)
async def add_jobs(session_id: str, request: AddJobsRequest, service: SessionService = Depends(get_session_service)) -> AddJobsResponse:
    postings = await service.add_jobs(session_id, request.jobs)
    summaries = [JobSummary.from_posting(posting) for posting in postings]
    return AddJobsResponse(jobs=summaries, needs_manual_paste=[summary.id for summary in summaries if summary.needs_manual_paste])

@router.put("/{session_id}/jobs/{job_id}/text", response_model=JobSummary)
async def update_job_text(session_id: str, job_id: str, request: UpdateJobTextRequest, service: SessionService = Depends(get_session_service)) -> JobSummary:
    return JobSummary.from_posting(await service.update_job_text(session_id, job_id, request.text))

@router.delete("/{session_id}/jobs/{job_id}", response_model=SessionResponse)
async def remove_job(session_id: str, job_id: str, service: SessionService = Depends(get_session_service), settings: Settings = Depends(get_settings)) -> SessionResponse:
    return SessionResponse.from_session(await service.remove_job(session_id, job_id), settings.session_ttl_minutes)
