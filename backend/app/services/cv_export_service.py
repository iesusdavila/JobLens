from pydantic import BaseModel
from app.core.exceptions import ExportNotAvailableError
from app.domain.cv_models import TailoredCv
from app.domain.enums import ExportFormat
from app.services.cv_templates.base import CvTemplate
from app.services.cv_templates.markdown_renderer import MarkdownCvRenderer

class ExportedFile(BaseModel):
    content: bytes
    media_type: str
    filename: str

class RenderedCvCache:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, ExportFormat], bytes] = {}

    def store(self, session_id: str, job_id: str, export_format: ExportFormat, content: bytes) -> None:
        self._entries[(session_id, job_id, export_format)] = content

    def get(self, session_id: str, job_id: str, export_format: ExportFormat) -> bytes | None:
        return self._entries.get((session_id, job_id, export_format))

    def drop_session(self, session_id: str) -> None:
        for key in [key for key in self._entries if key[0] == session_id]:
            del self._entries[key]

class CvExportService:
    MEDIA_TYPES = {
        ExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ExportFormat.PDF: "application/pdf",
        ExportFormat.MD: "text/markdown; charset=utf-8",
    }

    def __init__(self, templates: list[CvTemplate], markdown_renderer: MarkdownCvRenderer, cache: RenderedCvCache, default_template: str = "classic") -> None:
        self._templates = {template.name: template for template in templates}
        self._markdown_renderer = markdown_renderer
        self._cache = cache
        self._default_template = default_template

    def render_markdown(self, cv: TailoredCv) -> str:
        return self._markdown_renderer.render(cv)

    def render_and_store(self, session_id: str, job_id: str, cv: TailoredCv) -> str:
        markdown = self.render_markdown(cv)
        for export_format in ExportFormat:
            self._cache.store(session_id, job_id, export_format, self._render(cv, export_format, self._default_template, markdown))
        return markdown

    def export(self, session_id: str, job_id: str, cv: TailoredCv | None, export_format: ExportFormat, template_name: str | None = None) -> ExportedFile:
        if cv is None:
            raise ExportNotAvailableError("No tailored CV is available for this job yet. Run the analysis first.")
        cached = None if template_name else self._cache.get(session_id, job_id, export_format)
        content = cached or self._render(cv, export_format, template_name or self._default_template, None)
        return ExportedFile(content=content, media_type=self.MEDIA_TYPES[export_format], filename=self._filename(cv, export_format))

    def drop_session(self, session_id: str) -> None:
        self._cache.drop_session(session_id)

    def _render(self, cv: TailoredCv, export_format: ExportFormat, template_name: str, markdown: str | None) -> bytes:
        if export_format == ExportFormat.MD:
            return (markdown or self.render_markdown(cv)).encode("utf-8")
        template = self._templates.get(template_name)
        if template is None:
            raise ExportNotAvailableError(f"Unknown CV template '{template_name}'. Available: {', '.join(self._templates)}.")
        return template.render_docx(cv) if export_format == ExportFormat.DOCX else template.render_pdf(cv)

    @staticmethod
    def _filename(cv: TailoredCv, export_format: ExportFormat) -> str:
        base = "".join(char if char.isalnum() else "_" for char in (cv.full_name or "tailored")).strip("_") or "tailored"
        return f"{base}_cv.{export_format.value}"
