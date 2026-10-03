from app.domain.enums import ExportFormat
from app.services.cv_claims import CvClaimExtractor, CvClaimPruner
from app.services.cv_export_service import CvExportService, RenderedCvCache
from app.services.cv_fact_guard import CvFactGuard, TextMatcher
from app.services.cv_templates.classic_template import ClassicCvTemplate
from app.services.cv_templates.cv_blocks import CvBlockBuilder, CvSectionLabels
from app.services.cv_templates.markdown_renderer import ChangeLogRenderer, MarkdownCvRenderer
from tests.sample_data import candidate_profile, tailored_draft

def test_fact_guard_restores_facts_and_drops_inventions() -> None:
    result = CvFactGuard(TextMatcher()).enforce(tailored_draft(), candidate_profile())
    cv = result.draft.cv
    assert cv.full_name == "Jane Doe"
    assert [entry.employer for entry in cv.experiences] == ["Acme Corp", "Beta Labs"]
    assert cv.experiences[0].title == "Senior Backend Engineer"
    assert cv.certifications == []
    assert any("Invented Inc" in correction for correction in result.corrections)

def test_claim_pruner_removes_only_unsupported_items() -> None:
    cv = tailored_draft(fabricate=True).cv
    extractor = CvClaimExtractor()
    claims = extractor.extract(cv)
    fabricated = {claim.id for claim in claims if "FABRICATED" in claim.text}
    pruned = CvClaimPruner(extractor).prune(cv, claims, fabricated)
    assert len(pruned.experiences[0].bullets) == len(cv.experiences[0].bullets) - 1
    assert pruned.skills == cv.skills

def test_exports_render_all_formats() -> None:
    builder = CvBlockBuilder(CvSectionLabels())
    service = CvExportService([ClassicCvTemplate(builder)], MarkdownCvRenderer(builder), RenderedCvCache())
    cv = CvFactGuard(TextMatcher()).enforce(tailored_draft(), candidate_profile()).draft.cv
    markdown = service.render_and_store("s" * 32, "job1", cv)
    assert markdown.startswith("# Jane Doe")
    assert "## Experience" in markdown
    assert service.export("s" * 32, "job1", cv, ExportFormat.DOCX).content[:2] == b"PK"
    assert service.export("s" * 32, "job1", cv, ExportFormat.PDF).content[:5] == b"%PDF-"
    assert service.export("s" * 32, "job1", cv, ExportFormat.MD).media_type.startswith("text/markdown")

def test_spanish_cv_uses_spanish_headings() -> None:
    cv = tailored_draft().cv.model_copy(update={"language": "es"})
    assert "## Experiencia" in MarkdownCvRenderer(CvBlockBuilder(CvSectionLabels())).render(cv)

def test_change_log_is_diff_style() -> None:
    rendered = ChangeLogRenderer().render(tailored_draft().changes)
    assert "```diff" in rendered and "- Built FastAPI services" in rendered and "**Why:**" in rendered
