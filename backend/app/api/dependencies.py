from datetime import timedelta
import httpx
from fastapi import Request
from app.agents.analysis.analysis_agent import AnalysisAgent
from app.agents.analysis.finalizer import AnalysisFinalizer
from app.agents.analysis.stop_policy import AgentStopPolicy, NextStepAdvisor
from app.agents.analysis.tools import AnalysisToolkit, ToolFeedbackFormatter
from app.agents.chat.chat_agent import ChatAgent
from app.agents.chat.tools import WebSearchTool
from app.clients.llm_client import LlmClient
from app.clients.jev_client import JevClient
from app.config.settings import Settings
from app.repositories.file_session_repository import FileSessionRepository
from app.repositories.memory_session_repository import MemorySessionRepository
from app.repositories.session_repository import SessionLockRegistry, SessionRepository
from app.services.analysis_service import AnalysisService, RankingBuilder
from app.services.background_task_manager import BackgroundTaskManager
from app.services.chat_service import ApplicationChatService, ChatContextBuilder
from app.services.cv_claims import CvClaimExtractor, CvClaimPruner
from app.services.cv_evaluation_service import CvEvaluationService
from app.services.cv_export_service import CvExportService, RenderedCvCache
from app.services.cv_fact_guard import CvFactGuard, TextMatcher
from app.services.cv_tailoring_service import CvTailoringService
from app.services.cv_templates.classic_template import ClassicCvTemplate
from app.services.cv_templates.cv_blocks import CvBlockBuilder, CvSectionLabels
from app.services.cv_templates.markdown_renderer import ChangeLogRenderer, MarkdownCvRenderer
from app.services.document_parser_service import DocumentParserService, DocxDocumentParser, PdfDocumentParser, PlainTextDocumentParser, SectionSplitter, TextNormalizer
from app.services.fit_evaluation_service import FitEvaluationService
from app.services.job_ingestion_service import AccessBarrierDetector, JobIngestionService, JobPageTextExtractor, PastedTextJobProvider, RobotsPolicy, UrlJobFetcher
from app.services.job_requirement_extraction_service import JobRequirementExtractionService
from app.services.profile_extraction_service import ProfileExtractionService, SourceReferenceLocator
from app.services.session_cleanup_service import SessionCleanupService
from app.services.session_service import SessionService
from app.validators.ats_alignment_validator import AtsAlignmentValidator
from app.validators.cv_faithfulness_validator import CvFaithfulnessValidator
from app.validators.cv_quality_validator import CvQualityValidator
from app.validators.evidence_chunker import EvidenceChunker
from app.validators.fit_dimension_validator import FitDimensionValidator
from app.validators.fit_score_aggregator import FitScoreAggregator
from app.validators.red_flag_validator import RedFlagValidator
from app.validators.requirement_match_validator import RequirementMatchValidator
from app.validators.seniority_validator import SeniorityValidator

class ServiceContainer:
    def __init__(
        self,
        settings: Settings,
        jev_client: JevClient | None = None,
        llm_client: LlmClient | None = None,
        http_client: httpx.AsyncClient | None = None,
        web_search: WebSearchTool | None = None,
    ) -> None:
        self.settings = settings
        self.jev_client = jev_client or JevClient(settings)
        self.llm_client = llm_client or LlmClient(settings)
        self.http_client = http_client or httpx.AsyncClient(follow_redirects=True, timeout=settings.http_fetch_timeout_seconds, max_redirects=5)
        self.locks = SessionLockRegistry()
        self.task_manager = BackgroundTaskManager()
        self.repository = self._repository()
        self.markdown_renderer = MarkdownCvRenderer(CvBlockBuilder(CvSectionLabels()))
        self.export_service = CvExportService([ClassicCvTemplate(CvBlockBuilder(CvSectionLabels()))], self.markdown_renderer, RenderedCvCache())
        self.session_service = SessionService(self.repository, self._parser(), self._ingestion(), self.locks, self.export_service)
        self.analysis_agent = self._analysis_agent()
        self.analysis_service = AnalysisService(self.repository, self.analysis_agent, RankingBuilder(), self.locks, self.task_manager, settings.max_concurrent_jobs)
        self.chat_service = ApplicationChatService(self.repository, self._chat_agent(web_search), ChatContextBuilder(), self.locks, settings.chat_history_window)
        self.cleanup_service = SessionCleanupService(self.repository, self.export_service, self.locks, settings.session_cleanup_interval_seconds)

    async def aclose(self) -> None:
        await self.task_manager.shutdown()
        await self.http_client.aclose()
        await self.jev_client.aclose()

    def _repository(self) -> SessionRepository:
        ttl = timedelta(minutes=self.settings.session_ttl_minutes)
        if self.settings.session_storage == "file":
            return FileSessionRepository(ttl, self.settings.session_storage_path)
        return MemorySessionRepository(ttl)

    def _parser(self) -> DocumentParserService:
        parsers = [PdfDocumentParser(), DocxDocumentParser(), PlainTextDocumentParser()]
        return DocumentParserService(parsers, TextNormalizer(), SectionSplitter(), self.settings.max_upload_bytes)

    def _ingestion(self) -> JobIngestionService:
        normalizer = TextNormalizer()
        fetcher = UrlJobFetcher(
            self.http_client,
            RobotsPolicy(self.http_client, self.settings.respect_robots_txt),
            JobPageTextExtractor(normalizer),
            AccessBarrierDetector(self.settings.min_job_text_chars),
            self.settings.max_job_text_chars,
        )
        provider = PastedTextJobProvider(normalizer, self.settings.min_pasted_job_chars, self.settings.max_job_text_chars)
        return JobIngestionService(fetcher, provider, self.settings.max_jobs_per_session)

    def _analysis_agent(self) -> AnalysisAgent:
        settings = self.settings
        thresholds = settings.thresholds
        chunker = EvidenceChunker(max(1000, settings.jev_max_state_chars - 4000))
        ats_validator = AtsAlignmentValidator(self.jev_client, thresholds)
        fit_service = FitEvaluationService(
            RequirementMatchValidator(self.jev_client, thresholds, chunker),
            FitDimensionValidator(self.jev_client, thresholds),
            SeniorityValidator(self.jev_client, thresholds),
            RedFlagValidator(self.jev_client, thresholds),
            ats_validator,
            FitScoreAggregator(settings.fit_weights, settings.dimension_weights, settings.recommendation_thresholds),
        )
        claim_extractor = CvClaimExtractor()
        cv_evaluation = CvEvaluationService(
            CvFaithfulnessValidator(self.jev_client, thresholds, chunker),
            ats_validator,
            CvQualityValidator(self.jev_client, thresholds, settings.max_cv_words, settings.max_bullets_per_role),
            claim_extractor,
            self.markdown_renderer,
            thresholds.min_ats_improvement,
        )
        stop_policy = AgentStopPolicy(settings.max_agent_iterations, settings.max_agent_steps, settings.max_tool_errors, settings.max_agent_nudges)
        advisor = NextStepAdvisor(stop_policy)
        finalizer = AnalysisFinalizer(self.export_service, claim_extractor, CvClaimPruner(claim_extractor), ChangeLogRenderer(), settings.max_agent_iterations)
        toolkit = AnalysisToolkit(
            JobRequirementExtractionService(self.llm_client, settings.max_job_text_chars),
            ProfileExtractionService(self.llm_client, SourceReferenceLocator(), settings.max_source_text_chars),
            fit_service,
            CvTailoringService(self.llm_client, CvFactGuard(TextMatcher()), settings.max_source_text_chars, settings.max_cv_words, settings.max_bullets_per_role),
            cv_evaluation,
            finalizer,
            stop_policy,
            advisor,
            ToolFeedbackFormatter(),
        )
        recursion_limit = settings.max_agent_steps * 2 + settings.max_agent_nudges * 2 + 10
        return AnalysisAgent(self.llm_client, toolkit, finalizer, stop_policy, advisor, recursion_limit)

    def _chat_agent(self, web_search: WebSearchTool | None) -> ChatAgent:
        search_tool = web_search or (WebSearchTool(self.settings.web_search_max_results) if self.settings.enable_web_search else None)
        return ChatAgent(self.llm_client.conversation_model, search_tool, self.settings.chat_max_tool_rounds)

def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container

def get_settings(request: Request) -> Settings:
    return request.app.state.container.settings

def get_session_service(request: Request) -> SessionService:
    return request.app.state.container.session_service

def get_analysis_service(request: Request) -> AnalysisService:
    return request.app.state.container.analysis_service

def get_chat_service(request: Request) -> ApplicationChatService:
    return request.app.state.container.chat_service

def get_export_service(request: Request) -> CvExportService:
    return request.app.state.container.export_service
