from app.config.settings import ValidationThresholds
from app.domain.document_models import DocumentSection
from app.domain.enums import DocumentKind, IngestionStatus, JobSourceType, RequirementVerdict, SeniorityMatch
from app.domain.job_models import JobPosting
from app.domain.session_models import CandidatePreferences
from app.validators.ats_alignment_validator import AtsAlignmentValidator
from app.validators.evidence_chunker import EvidenceChunker
from app.validators.fit_dimension_validator import FitDimensionValidator
from app.validators.red_flag_validator import RedFlagValidator
from app.validators.requirement_match_validator import RequirementMatchValidator
from app.validators.seniority_validator import SeniorityValidator
from tests.fakes import FakeJevClient
from tests.sample_data import CV_TEXT, JOB_TEXT, candidate_profile, parsed_job

def evidence() -> list[DocumentSection]:
    return [DocumentSection(id="cv-s1", source=DocumentKind.CV, heading="All", text=CV_TEXT)]

async def test_requirement_match_classifies_met_partial_missing() -> None:
    jev = FakeJevClient(overrides={"M2": 0.5})
    validator = RequirementMatchValidator(jev, ValidationThresholds(), EvidenceChunker(50000))
    assessments = {item.requirement_id: item for item in await validator.validate(parsed_job(), evidence())}
    assert assessments["M1"].verdict == RequirementVerdict.MET
    assert assessments["M2"].verdict == RequirementVerdict.PARTIAL
    assert assessments["M4"].verdict == RequirementVerdict.MISSING
    assert assessments["N1"].priority.value == "nice_to_have"
    assert len(jev.calls) == 1

async def test_requirement_match_takes_best_evidence_across_chunks() -> None:
    jev = FakeJevClient()
    sections = [
        DocumentSection(id="cv-s1", source=DocumentKind.CV, heading="A", text="Kubernetes in production for 3 years. " * 30),
        DocumentSection(id="cv-s2", source=DocumentKind.CV, heading="B", text="Unrelated hobby text. " * 40),
    ]
    validator = RequirementMatchValidator(jev, ValidationThresholds(), EvidenceChunker(1200))
    assessments = {item.requirement_id: item for item in await validator.validate(parsed_job(), sections)}
    assert len(jev.calls) == 2
    assert assessments["M4"].verdict == RequirementVerdict.MET

async def test_fit_dimensions_return_one_score_per_dimension() -> None:
    validator = FitDimensionValidator(FakeJevClient(), ValidationThresholds())
    assessments = await validator.validate(parsed_job(), candidate_profile())
    assert {item.dimension.value for item in assessments} == {"technical", "domain", "tools", "soft_skills"}
    assert all(0.0 <= item.score <= 1.0 for item in assessments)
    assert all(not item.low_confidence for item in assessments)

async def test_seniority_uses_choice_and_years_noul() -> None:
    jev = FakeJevClient(overrides={"years_requirement": 0.9})
    assessment = await SeniorityValidator(jev, ValidationThresholds()).validate(parsed_job(), candidate_profile())
    assert assessment.match == SeniorityMatch.MATCHES
    assert assessment.years_requirement_probability == 0.9
    question_keys = {question.key for question in jev.calls[0][1]}
    assert question_keys == {"seniority_level", "years_requirement"}

async def test_red_flags_skip_preference_questions_without_preferences() -> None:
    jev = FakeJevClient(overrides={"vague_responsibilities": 0.8})
    job = JobPosting(source_type=JobSourceType.TEXT, text=JOB_TEXT, ingestion_status=IngestionStatus.OK)
    flags = await RedFlagValidator(jev, ValidationThresholds()).validate(job, parsed_job(), candidate_profile(), CandidatePreferences())
    codes = {flag.code for flag in flags}
    assert "location_conflict" not in codes
    assert {"unexplained_gaps", "missing_must_haves", "suspicious_posting"} <= codes
    assert [flag.code for flag in flags if flag.triggered] == ["vague_responsibilities"]

async def test_red_flags_include_preference_conflicts_when_provided() -> None:
    job = JobPosting(source_type=JobSourceType.TEXT, text=JOB_TEXT, ingestion_status=IngestionStatus.OK)
    preferences = CandidatePreferences(desired_locations=["Madrid"], preferred_modality="onsite")
    flags = await RedFlagValidator(FakeJevClient(), ValidationThresholds()).validate(job, parsed_job(), candidate_profile(), preferences)
    assert {"location_conflict", "modality_conflict", "salary_conflict"} <= {flag.code for flag in flags}

async def test_ats_alignment_reports_keyword_coverage() -> None:
    alignment = await AtsAlignmentValidator(FakeJevClient(), ValidationThresholds()).validate(parsed_job(), CV_TEXT)
    assert set(alignment.matched_keywords) == {"Python", "FastAPI", "PostgreSQL"}
    assert set(alignment.missing_keywords) == {"Kubernetes", "microservices", "CI/CD"}
    assert alignment.keyword_coverage == 0.5
    assert 0.0 < alignment.score < 1.0
