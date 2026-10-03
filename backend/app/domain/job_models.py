from uuid import uuid4
from pydantic import BaseModel, Field, field_validator, model_validator
from app.domain.enums import IngestionStatus, JobSourceType, RequirementPriority

class JobInput(BaseModel):
    url: str | None = None
    text: str | None = None
    label: str | None = Field(default=None, max_length=200)

    @field_validator("url", "text", "label", mode="before")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_exactly_one_source(self) -> "JobInput":
        if bool(self.url) == bool(self.text):
            raise ValueError("Provide either a job URL or the pasted job text, not both and not neither.")
        if self.url and not self.url.lower().startswith(("http://", "https://")):
            raise ValueError("The job URL must start with http:// or https://.")
        return self

class JobPosting(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    source_type: JobSourceType
    url: str | None = None
    label: str | None = None
    text: str = ""
    ingestion_status: IngestionStatus
    message: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.ingestion_status == IngestionStatus.OK and bool(self.text.strip())

    @property
    def display_name(self) -> str:
        return self.label or self.url or f"Pasted job {self.id}"

class JobRequirement(BaseModel):
    id: str
    text: str
    priority: RequirementPriority

class ParsedJob(BaseModel):
    title: str = Field(description="Job title exactly as stated in the posting.")
    company: str | None = Field(default=None, description="Hiring company name, null if not stated.")
    seniority_level: str | None = Field(default=None, description="Seniority such as intern, junior, mid, senior, lead, principal. Null if not stated or implied.")
    min_years_experience: float | None = Field(default=None, description="Minimum years of experience required, null if not stated.")
    must_have_requirements: list[str] = Field(default_factory=list, description="Explicitly required qualifications, one atomic requirement per item.")
    nice_to_have_requirements: list[str] = Field(default_factory=list, description="Preferred or bonus qualifications, one atomic requirement per item.")
    responsibilities: list[str] = Field(default_factory=list, description="Main responsibilities of the role.")
    keywords: list[str] = Field(default_factory=list, description="Up to 20 key terms (skills, tools, methods, domain words) written exactly as in the posting.")
    domain: str | None = Field(default=None, description="Industry or business domain of the role, null if unclear.")
    location: str | None = Field(default=None, description="Job location, null if not stated.")
    modality: str | None = Field(default=None, description="remote, hybrid or onsite, null if not stated.")
    salary: str | None = Field(default=None, description="Salary or compensation exactly as stated, null if absent.")

    def requirements(self) -> list[JobRequirement]:
        must_haves = [
            JobRequirement(id=f"M{index}", text=text, priority=RequirementPriority.MUST_HAVE)
            for index, text in enumerate(self.must_have_requirements, start=1)
        ]
        nice_to_haves = [
            JobRequirement(id=f"N{index}", text=text, priority=RequirementPriority.NICE_TO_HAVE)
            for index, text in enumerate(self.nice_to_have_requirements, start=1)
        ]
        return must_haves + nice_to_haves

    def summary_state(self) -> dict[str, object]:
        return {
            "title": self.title,
            "company": self.company,
            "domain": self.domain,
            "seniority_level": self.seniority_level,
            "min_years_experience": self.min_years_experience,
            "must_have_requirements": self.must_have_requirements,
            "nice_to_have_requirements": self.nice_to_have_requirements,
            "responsibilities": self.responsibilities[:10],
            "keywords": self.keywords,
        }

    def key_terms(self) -> list[str]:
        return self.keywords or self.must_have_requirements
