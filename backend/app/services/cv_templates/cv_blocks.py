from enum import StrEnum
from pydantic import BaseModel
from app.domain.cv_models import TailoredCv

class CvBlockKind(StrEnum):
    NAME = "name"
    CONTACT = "contact"
    HEADLINE = "headline"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    ENTRY = "entry"
    ENTRY_META = "entry_meta"
    BULLET = "bullet"

class CvBlock(BaseModel):
    kind: CvBlockKind
    text: str

class CvSectionLabels:
    LABELS = {
        "en": {"summary": "Summary", "skills": "Skills", "experience": "Experience", "projects": "Projects", "education": "Education", "certifications": "Certifications", "languages": "Languages", "present": "Present"},
        "es": {"summary": "Perfil profesional", "skills": "Habilidades", "experience": "Experiencia", "projects": "Proyectos", "education": "Educación", "certifications": "Certificaciones", "languages": "Idiomas", "present": "Actualidad"},
        "pt": {"summary": "Resumo", "skills": "Competências", "experience": "Experiência", "projects": "Projetos", "education": "Formação", "certifications": "Certificações", "languages": "Idiomas", "present": "Atual"},
        "fr": {"summary": "Profil", "skills": "Compétences", "experience": "Expérience", "projects": "Projets", "education": "Formation", "certifications": "Certifications", "languages": "Langues", "present": "Présent"},
    }

    def for_language(self, language: str) -> dict[str, str]:
        return self.LABELS.get(language.lower()[:2], self.LABELS["en"])

class CvBlockBuilder:
    def __init__(self, labels: CvSectionLabels) -> None:
        self._labels = labels

    def build(self, cv: TailoredCv) -> list[CvBlock]:
        labels = self._labels.for_language(cv.language)
        blocks = self._header(cv)
        if cv.summary:
            blocks += [CvBlock(kind=CvBlockKind.HEADING, text=labels["summary"]), CvBlock(kind=CvBlockKind.PARAGRAPH, text=cv.summary)]
        if cv.skills:
            blocks += [CvBlock(kind=CvBlockKind.HEADING, text=labels["skills"]), CvBlock(kind=CvBlockKind.PARAGRAPH, text=", ".join(cv.skills))]
        blocks += self._experience(cv, labels)
        blocks += self._projects(cv, labels)
        blocks += self._education(cv, labels)
        blocks += self._simple_list(labels["certifications"], cv.certifications)
        if cv.languages:
            blocks += [CvBlock(kind=CvBlockKind.HEADING, text=labels["languages"]), CvBlock(kind=CvBlockKind.PARAGRAPH, text=", ".join(cv.languages))]
        return blocks

    def _header(self, cv: TailoredCv) -> list[CvBlock]:
        blocks = []
        if cv.full_name:
            blocks.append(CvBlock(kind=CvBlockKind.NAME, text=cv.full_name))
        if cv.headline:
            blocks.append(CvBlock(kind=CvBlockKind.HEADLINE, text=cv.headline))
        if cv.contact_line:
            blocks.append(CvBlock(kind=CvBlockKind.CONTACT, text=cv.contact_line))
        return blocks

    def _experience(self, cv: TailoredCv, labels: dict[str, str]) -> list[CvBlock]:
        if not cv.experiences:
            return []
        blocks = [CvBlock(kind=CvBlockKind.HEADING, text=labels["experience"])]
        for entry in cv.experiences:
            blocks.append(CvBlock(kind=CvBlockKind.ENTRY, text=f"{entry.title} | {entry.employer}"))
            meta = self._join(self._date_range(entry.start_date, entry.end_date), entry.location)
            if meta:
                blocks.append(CvBlock(kind=CvBlockKind.ENTRY_META, text=meta))
            blocks += [CvBlock(kind=CvBlockKind.BULLET, text=bullet) for bullet in entry.bullets]
        return blocks

    def _projects(self, cv: TailoredCv, labels: dict[str, str]) -> list[CvBlock]:
        if not cv.projects:
            return []
        blocks = [CvBlock(kind=CvBlockKind.HEADING, text=labels["projects"])]
        for project in cv.projects:
            blocks.append(CvBlock(kind=CvBlockKind.ENTRY, text=project.name))
            blocks += [CvBlock(kind=CvBlockKind.BULLET, text=bullet) for bullet in project.bullets]
        return blocks

    def _education(self, cv: TailoredCv, labels: dict[str, str]) -> list[CvBlock]:
        if not cv.education:
            return []
        blocks = [CvBlock(kind=CvBlockKind.HEADING, text=labels["education"])]
        for entry in cv.education:
            blocks.append(CvBlock(kind=CvBlockKind.ENTRY, text=f"{entry.degree} | {entry.institution}"))
            meta = self._date_range(entry.start_date, entry.end_date)
            if meta:
                blocks.append(CvBlock(kind=CvBlockKind.ENTRY_META, text=meta))
            blocks += [CvBlock(kind=CvBlockKind.BULLET, text=detail) for detail in entry.details]
        return blocks

    @staticmethod
    def _simple_list(heading: str, items: list[str]) -> list[CvBlock]:
        if not items:
            return []
        return [CvBlock(kind=CvBlockKind.HEADING, text=heading)] + [CvBlock(kind=CvBlockKind.BULLET, text=item) for item in items]

    @staticmethod
    def _date_range(start: str | None, end: str | None) -> str:
        return " - ".join(value for value in (start, end) if value)

    @staticmethod
    def _join(*parts: str | None) -> str:
        return " | ".join(part for part in parts if part)
