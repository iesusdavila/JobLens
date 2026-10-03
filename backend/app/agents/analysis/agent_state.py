from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel
from app.domain.analysis_models import JobAnalysisResult
from app.domain.cv_models import TailoredCvDraft
from app.domain.document_models import ParsedDocument
from app.domain.enums import AgentStatus
from app.domain.job_models import JobPosting, JobRequirement, ParsedJob
from app.domain.profile_models import CandidateProfile
from app.domain.session_models import CandidatePreferences
from app.domain.validation_models import CvValidationReport, FitAnalysis

class ScoredDraft(BaseModel):
    draft: TailoredCvDraft
    report: CvValidationReport
    iteration: int

class AnalysisAgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    session_id: str
    job: JobPosting
    cv_document: ParsedDocument
    extra_document: ParsedDocument | None
    preferences: CandidatePreferences
    parsed_job: ParsedJob | None
    requirements: list[JobRequirement]
    profile: CandidateProfile | None
    fit_analysis: FitAnalysis | None
    draft: TailoredCvDraft | None
    cv_validation: CvValidationReport | None
    best_attempt: ScoredDraft | None
    last_feedback: list[str]
    iteration: int
    agent_steps: int
    nudges: int
    tool_errors: int
    agent_failed: bool
    last_error: str | None
    warnings: list[str]
    status: AgentStatus
    result: JobAnalysisResult | None
