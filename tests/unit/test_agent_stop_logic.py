from app.agents.analysis.agent_state import ScoredDraft
from app.agents.analysis.stop_policy import AgentStopPolicy, NextStepAdvisor
from app.clients.jev_questions import JevQuestion, JevState
from app.core.exceptions import JevServiceError
from app.domain.document_models import ParsedDocument
from app.domain.enums import DocumentKind, IngestionStatus, JobAnalysisStatus, JobSourceType
from app.domain.job_models import JobPosting
from app.domain.session_models import CandidatePreferences
from app.domain.validation_models import AtsAlignment, ClaimCheck, CvQualityReport, CvValidationReport, JevEvaluation
from app.services.document_parser_service import SectionSplitter, TextNormalizer
from tests.conftest import build_llm
from tests.fakes import FakeJevClient, PolicyAgentModel
from tests.sample_data import CV_TEXT, JOB_TEXT, parsed_job, tailored_draft

def report(supported: bool, improved: bool, ats: float = 0.6) -> CvValidationReport:
    alignment = AtsAlignment(score=ats, keyword_coverage=ats, terminology_mirroring=ats, priority_alignment=ats, confidence=0.8)
    checks = [ClaimCheck(claim_id="c1", text="claim", section="summary", support_probability=0.9 if supported else 0.1, supported=supported)]
    return CvValidationReport(claim_checks=checks, ats_original=alignment, ats_tailored=alignment, ats_improved=improved, quality=CvQualityReport(checks=[]))

def job() -> JobPosting:
    return JobPosting(source_type=JobSourceType.TEXT, text=JOB_TEXT, ingestion_status=IngestionStatus.OK)

class BrokenJevClient(FakeJevClient):
    async def evaluate(self, state: JevState, questions: list[JevQuestion]) -> JevEvaluation:
        raise JevServiceError("Jev validation service returned HTTP 529.")

def cv_document() -> ParsedDocument:
    text = TextNormalizer().normalize(CV_TEXT)
    return ParsedDocument(kind=DocumentKind.CV, filename="cv.txt", text=text, sections=SectionSplitter().split(text, DocumentKind.CV))

def test_policy_finalizes_only_when_faithful_and_improved() -> None:
    policy = AgentStopPolicy(max_iterations=3, max_steps=20, max_tool_errors=3, max_nudges=2)
    assert policy.validation_passed(report(True, True))
    assert not policy.validation_passed(report(False, True))
    assert not policy.validation_passed(report(True, False))
    assert not policy.validation_passed(None)

def test_policy_allows_finalize_on_cap_or_error() -> None:
    policy = AgentStopPolicy(max_iterations=2, max_steps=20, max_tool_errors=3, max_nudges=2)
    fit_ready = {"fit_analysis": object(), "cv_validation": report(False, False)}
    assert not policy.may_finalize({**fit_ready, "iteration": 1})
    assert policy.may_finalize({**fit_ready, "iteration": 2})
    assert policy.may_finalize({**fit_ready, "iteration": 1, "last_error": "Jev down"})
    assert not policy.may_finalize({"iteration": 5})

def test_best_attempt_prefers_faithful_then_ats() -> None:
    policy = AgentStopPolicy(max_iterations=3, max_steps=20, max_tool_errors=3, max_nudges=2)
    unfaithful = ScoredDraft(draft=tailored_draft(), report=report(False, True, ats=0.9), iteration=1)
    faithful = ScoredDraft(draft=tailored_draft(), report=report(True, False, ats=0.5), iteration=2)
    assert policy.best_of(unfaithful, faithful) is faithful
    assert policy.best_of(faithful, unfaithful) is faithful

def test_advisor_follows_prerequisites() -> None:
    advisor = NextStepAdvisor(AgentStopPolicy(max_iterations=3, max_steps=20, max_tool_errors=3, max_nudges=2))
    assert advisor.suggest({}) == "extract_job_requirements"
    assert advisor.suggest({"parsed_job": parsed_job()}) == "parse_candidate_profile"

async def test_agent_revises_after_failed_validation_then_finalizes(container_factory) -> None:
    groq = build_llm()
    container = container_factory(llm=groq)
    result = await container.analysis_agent.run("a" * 32, job(), cv_document(), None, CandidatePreferences())
    assert result.status == JobAnalysisStatus.COMPLETED
    assert result.iterations == 2
    assert result.cv_validation.ready_to_finalize
    assert result.tailored_cv.full_name == "Jane Doe"
    assert [entry.employer for entry in result.tailored_cv.experiences] == ["Acme Corp", "Beta Labs"]
    assert result.tailored_cv.experiences[0].title == "Senior Backend Engineer"
    assert result.tailored_cv.certifications == []
    assert "Kubernetes" not in result.markdown_preview

async def test_agent_stops_at_iteration_cap_and_prunes_unsupported_claims(container_factory) -> None:
    container = container_factory(llm=build_llm(fabricate_always=True), max_agent_iterations=2)
    result = await container.analysis_agent.run("b" * 32, job(), cv_document(), None, CandidatePreferences())
    assert result.status == JobAnalysisStatus.COMPLETED_WITH_WARNINGS
    assert result.iterations == 2
    assert any("Unresolved issues" in warning for warning in result.warnings)
    assert all("FABRICATED" not in bullet for entry in result.tailored_cv.experiences for bullet in entry.bullets)

async def test_agent_failure_is_reported_gracefully(container_factory) -> None:
    container = container_factory(llm=build_llm(agent_model=PolicyAgentModel(fail=True)))
    result = await container.analysis_agent.run("c" * 32, job(), cv_document(), None, CandidatePreferences())
    assert result.status == JobAnalysisStatus.FAILED
    assert "unreachable" in result.error

async def test_agent_that_stops_talking_is_nudged_then_force_finalized(container_factory) -> None:
    container = container_factory(llm=build_llm(agent_model=PolicyAgentModel(stop_without_tools_after=3)))
    result = await container.analysis_agent.run("d" * 32, job(), cv_document(), None, CandidatePreferences())
    assert result.fit is not None
    assert result.tailored_cv is None
    assert any("stopped before finishing" in warning for warning in result.warnings)

async def test_jev_outage_finalizes_after_tool_error_budget(container_factory) -> None:
    container = container_factory(jev=BrokenJevClient())
    result = await container.analysis_agent.run("e" * 32, job(), cv_document(), None, CandidatePreferences())
    assert result.status == JobAnalysisStatus.FAILED
    assert "529" in result.error

async def test_parallel_tool_calls_run_one_and_keep_history_append_only(container_factory) -> None:
    container = container_factory(llm=build_llm(agent_model=PolicyAgentModel(duplicate_tool_calls=True)))
    result = await container.analysis_agent.run("f" * 32, job(), cv_document(), None, CandidatePreferences())
    assert result.status == JobAnalysisStatus.COMPLETED
    assert result.tailored_cv is not None
