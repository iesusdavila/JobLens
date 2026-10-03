from pydantic import BaseModel, Field
from app.domain.profile_models import EducationEntry

class TailoredExperience(BaseModel):
    title: str
    employer: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    bullets: list[str] = Field(default_factory=list)

class TailoredProject(BaseModel):
    name: str
    bullets: list[str] = Field(default_factory=list)

class TailoredCv(BaseModel):
    language: str = Field(default="en", description="ISO 639-1 code of the language the CV is written in, the same as the source CV.")
    full_name: str | None = None
    contact_line: str | None = None
    headline: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    experiences: list[TailoredExperience] = Field(default_factory=list)
    projects: list[TailoredProject] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

class CvChange(BaseModel):
    section: str = Field(description="CV section affected, for example summary, skills, experience.")
    original: str | None = Field(default=None, description="Original text, null when the item was only reordered or condensed from several items.")
    tailored: str | None = Field(default=None, description="New text, null when the item was removed.")
    reason: str = Field(description="Why this change makes the CV fit the job better.")

class TailoredCvDraft(BaseModel):
    cv: TailoredCv
    changes: list[CvChange] = Field(default_factory=list)

class CvClaim(BaseModel):
    id: str
    text: str
    section: str
    item_index: int | None = None
    bullet_index: int | None = None
