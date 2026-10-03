from fastapi import APIRouter, Depends, Query, Response, status
from app.api.dependencies import get_analysis_service, get_export_service
from app.api.schemas.analysis_schemas import AnalysisResultsResponse, AnalysisStatusResponse
from app.domain.enums import ExportFormat
from app.services.analysis_service import AnalysisService
from app.services.cv_export_service import CvExportService

router = APIRouter(prefix="/sessions", tags=["analysis"])

@router.post("/{session_id}/analyze", response_model=AnalysisResultsResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze(
    session_id: str,
    background: bool = Query(default=True, description="Run in the background and poll /status, or wait for the results."),
    service: AnalysisService = Depends(get_analysis_service),
) -> AnalysisResultsResponse:
    return AnalysisResultsResponse.from_run(await service.start(session_id, background))

@router.get("/{session_id}/status", response_model=AnalysisStatusResponse)
async def analysis_status(session_id: str, service: AnalysisService = Depends(get_analysis_service)) -> AnalysisStatusResponse:
    return AnalysisStatusResponse.from_run(service.status(session_id))

@router.get("/{session_id}/results", response_model=AnalysisResultsResponse)
async def analysis_results(session_id: str, service: AnalysisService = Depends(get_analysis_service)) -> AnalysisResultsResponse:
    return AnalysisResultsResponse.from_run(service.results(session_id))

@router.get("/{session_id}/jobs/{job_id}/cv")
async def download_cv(
    session_id: str,
    job_id: str,
    format: ExportFormat = Query(default=ExportFormat.DOCX),
    template: str | None = Query(default=None),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    export_service: CvExportService = Depends(get_export_service),
) -> Response:
    result = analysis_service.results(session_id).results.get(job_id)
    exported = export_service.export(session_id, job_id, result.tailored_cv if result else None, format, template)
    headers = {"Content-Disposition": f'attachment; filename="{exported.filename}"'}
    return Response(content=exported.content, media_type=exported.media_type, headers=headers)
