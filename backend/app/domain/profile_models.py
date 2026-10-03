from pydantic import BaseModel, Field

class ExperienceEntry(BaseModel):
    title: str = Field(description="Job title exactly as written in the source.")
    employer: str = Field(description="Employer name exactly as written in the source.")
    location: str | None = None
    start_date: str | None = Field(default=None, description="Start date exactly as written in the source.")
    end_date: str | None = Field(default=None, description="End date exactly as written, or 'Present'.")
    highlights: list[str] = Field(default_factory=list, description="Responsibilities and achievements, close to the source wording.")
    source_refs: list[str] = Field(default_factory=list, description="Leave empty. Filled by the system.")

class EducationEntry(BaseModel):
    degree: str
    institution: str
    start_date: str | None = None
    end_date: str | None = None
    details: list[str] = Field(default_factory=list)

class ProjectEntry(BaseModel):
    name: str
    description: str | None = None
    highlights: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list, description="Leave empty. Filled by the system.")

class CandidateProfile(BaseModel):
    full_name: str | None = None
    contact_line: str | None = Field(default=None, description="Email, phone, city and links as one line, exactly as in the source.")
    headline: str | None = None
    summary: str | None = None
    total_years_experience: float | None = Field(default=None, description="Total years of professional experience if it can be derived from the dates, else null.")
    skills: list[str] = Field(default_factory=list)
    experiences: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    additional_facts: list[str] = Field(default_factory=list, description="Achievements or facts found only in the extra document.")

    @property
    def is_empty(self) -> bool:
        return not (self.experiences or self.skills or self.education or self.projects)

    def compact_state(self, max_highlights_per_item: int = 6) -> dict[str, object]:
        return {
            "headline": self.headline,
            "summary": self.summary,
            "total_years_experience": self.total_years_experience,
            "skills": self.skills,
            "experiences": [
                {
                    "title": entry.title,
                    "employer": entry.employer,
                    "start_date": entry.start_date,
                    "end_date": entry.end_date,
                    "highlights": entry.highlights[:max_highlights_per_item],
                }
                for entry in self.experiences
            ],
            "projects": [
                {"name": entry.name, "description": entry.description, "highlights": entry.highlights[:max_highlights_per_item]}
                for entry in self.projects
            ],
            "education": [entry.model_dump(exclude={"details"}) for entry in self.education],
            "certifications": self.certifications,
            "languages": self.languages,
            "additional_facts": self.additional_facts,
        }

    def timeline_state(self) -> list[dict[str, str | None]]:
        return [
            {"title": entry.title, "employer": entry.employer, "start_date": entry.start_date, "end_date": entry.end_date}
            for entry in self.experiences
        ]
