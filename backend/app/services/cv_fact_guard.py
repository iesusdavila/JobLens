import re
from pydantic import BaseModel
from app.domain.cv_models import TailoredCv, TailoredCvDraft, TailoredExperience
from app.domain.profile_models import CandidateProfile, EducationEntry, ExperienceEntry

class FactGuardResult(BaseModel):
    draft: TailoredCvDraft
    corrections: list[str]

class TextMatcher:
    def normalize(self, value: str | None) -> str:
        return re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    def matches(self, left: str | None, right: str | None) -> bool:
        first, second = self.normalize(left), self.normalize(right)
        if not first or not second:
            return False
        return first == second or first in second or second in first

class CvFactGuard:
    def __init__(self, matcher: TextMatcher) -> None:
        self._matcher = matcher

    def enforce(self, draft: TailoredCvDraft, profile: CandidateProfile) -> FactGuardResult:
        corrections: list[str] = []
        cv = draft.cv.model_copy(deep=True)
        cv.full_name = profile.full_name
        cv.contact_line = profile.contact_line
        cv.experiences = self._guard_experiences(cv, profile, corrections)
        cv.education = self._guard_education(cv.education, profile.education, corrections)
        cv.certifications = self._keep_known(cv.certifications, profile.certifications, "certification", corrections)
        cv.languages = self._keep_known(cv.languages, profile.languages, "language", corrections)
        return FactGuardResult(draft=TailoredCvDraft(cv=cv, changes=draft.changes), corrections=corrections)

    def _guard_experiences(self, cv: TailoredCv, profile: CandidateProfile, corrections: list[str]) -> list[TailoredExperience]:
        guarded = []
        for entry in cv.experiences:
            source = self._find_experience(entry, profile.experiences)
            if source is None:
                corrections.append(f"Removed experience not found in the source documents: {entry.title} at {entry.employer}.")
                continue
            if (entry.title, entry.employer, entry.start_date, entry.end_date) != (source.title, source.employer, source.start_date, source.end_date):
                corrections.append(f"Restored the original title, employer and dates for {source.employer}.")
            guarded.append(entry.model_copy(update={"title": source.title, "employer": source.employer, "start_date": source.start_date, "end_date": source.end_date, "location": source.location}))
        return guarded

    def _find_experience(self, entry: TailoredExperience, sources: list[ExperienceEntry]) -> ExperienceEntry | None:
        employer_matches = [source for source in sources if self._matcher.matches(entry.employer, source.employer)]
        if len(employer_matches) <= 1:
            return employer_matches[0] if employer_matches else None
        same_dates = [source for source in employer_matches if self._matcher.matches(entry.start_date, source.start_date)]
        same_title = [source for source in employer_matches if self._matcher.matches(entry.title, source.title)]
        return (same_dates or same_title or employer_matches)[0]

    def _guard_education(self, entries: list[EducationEntry], sources: list[EducationEntry], corrections: list[str]) -> list[EducationEntry]:
        guarded = []
        for entry in entries:
            source = next((item for item in sources if self._matcher.matches(entry.institution, item.institution)), None)
            if source is None:
                corrections.append(f"Removed education not found in the source documents: {entry.degree} at {entry.institution}.")
                continue
            guarded.append(entry.model_copy(update={"degree": source.degree, "institution": source.institution, "start_date": source.start_date, "end_date": source.end_date}))
        return guarded

    def _keep_known(self, items: list[str], known: list[str], label: str, corrections: list[str]) -> list[str]:
        kept = []
        for item in items:
            if any(self._matcher.matches(item, source) for source in known):
                kept.append(item)
            else:
                corrections.append(f"Removed {label} not found in the source documents: {item}.")
        return kept
