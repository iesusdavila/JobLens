from app.config.settings import ValidationThresholds
from app.domain.document_models import DocumentSection
from app.domain.enums import DocumentKind
from app.services.cv_claims import CvClaimExtractor
from app.services.cv_templates.cv_blocks import CvBlockBuilder, CvSectionLabels
from app.services.cv_templates.markdown_renderer import MarkdownCvRenderer
from app.validators.cv_faithfulness_validator import CvFaithfulnessValidator
from app.validators.cv_quality_validator import CvQualityValidator
from app.validators.evidence_chunker import EvidenceChunker
from tests.fakes import FakeJevClient
from tests.sample_data import CV_TEXT, parsed_job, tailored_draft

SOURCES = [DocumentSection(id="cv-s1", source=DocumentKind.CV, heading="All", text=CV_TEXT)]

async def test_faithfulness_flags_fabricated_claims() -> None:
    claims = CvClaimExtractor().extract(tailored_draft(fabricate=True).cv)
    checks = await CvFaithfulnessValidator(FakeJevClient(), ValidationThresholds(), EvidenceChunker(50000)).validate(claims, SOURCES)
    unsupported = [check for check in checks if not check.supported]
    assert len(checks) == len(claims)
    assert len(unsupported) == 1
    assert "Kubernetes" in unsupported[0].text

async def test_faithfulness_without_sources_marks_everything_unsupported() -> None:
    claims = CvClaimExtractor().extract(tailored_draft().cv)
    checks = await CvFaithfulnessValidator(FakeJevClient(), ValidationThresholds(), EvidenceChunker(50000)).validate(claims, [])
    assert checks and not any(check.supported for check in checks)

async def test_quality_combines_jev_and_code_checks() -> None:
    draft = tailored_draft()
    markdown = MarkdownCvRenderer(CvBlockBuilder(CvSectionLabels())).render(draft.cv)
    report = await CvQualityValidator(FakeJevClient(), ValidationThresholds(), max_words=900, max_bullets_per_role=6).validate(parsed_job(), draft.cv, markdown)
    assert {check.name for check in report.checks} == {"relevance_ordering", "no_filler", "clarity", "length", "bullets_per_role"}
    assert report.passed

async def test_quality_fails_length_when_cv_is_too_long() -> None:
    draft = tailored_draft()
    report = await CvQualityValidator(FakeJevClient(), ValidationThresholds(), max_words=10, max_bullets_per_role=2).validate(parsed_job(), draft.cv, "word " * 50)
    failing = {check.name for check in report.failing_checks()}
    assert failing == {"length", "bullets_per_role"}
