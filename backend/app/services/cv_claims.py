import re
from app.domain.cv_models import CvClaim, TailoredCv

class CvClaimExtractor:
    SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

    def extract(self, cv: TailoredCv) -> list[CvClaim]:
        claims: list[CvClaim] = []
        if cv.headline:
            self._add(claims, f"Professional headline: {cv.headline}", "headline")
        for index, sentence in enumerate(self.summary_sentences(cv)):
            self._add(claims, sentence, "summary", item_index=index)
        for index, skill in enumerate(cv.skills):
            self._add(claims, f"The candidate has experience with or knowledge of {skill}.", "skills", item_index=index)
        for item_index, entry in enumerate(cv.experiences):
            for bullet_index, bullet in enumerate(entry.bullets):
                self._add(claims, f"As {entry.title} at {entry.employer}: {bullet}", "experience", item_index, bullet_index)
        for item_index, project in enumerate(cv.projects):
            for bullet_index, bullet in enumerate(project.bullets):
                self._add(claims, f"In the project {project.name}: {bullet}", "projects", item_index, bullet_index)
        for index, entry in enumerate(cv.education):
            self._add(claims, f"The candidate studied {entry.degree} at {entry.institution}.", "education", item_index=index)
        for index, certification in enumerate(cv.certifications):
            self._add(claims, f"The candidate holds the certification {certification}.", "certifications", item_index=index)
        return claims

    def summary_sentences(self, cv: TailoredCv) -> list[str]:
        if not cv.summary:
            return []
        return [sentence.strip() for sentence in self.SENTENCE_SPLIT.split(cv.summary) if sentence.strip()]

    @staticmethod
    def _add(claims: list[CvClaim], text: str, section: str, item_index: int | None = None, bullet_index: int | None = None) -> None:
        claims.append(CvClaim(id=f"c{len(claims) + 1}", text=text, section=section, item_index=item_index, bullet_index=bullet_index))

class CvClaimPruner:
    def __init__(self, extractor: CvClaimExtractor) -> None:
        self._extractor = extractor

    def prune(self, cv: TailoredCv, claims: list[CvClaim], unsupported_ids: set[str]) -> TailoredCv:
        removed = [claim for claim in claims if claim.id in unsupported_ids]
        if not removed:
            return cv
        pruned = cv.model_copy(deep=True)
        pruned.headline = None if any(claim.section == "headline" for claim in removed) else pruned.headline
        pruned.summary = self._prune_summary(cv, removed)
        pruned.skills = self._drop_indexes(pruned.skills, self._indexes(removed, "skills"))
        pruned.certifications = self._drop_indexes(pruned.certifications, self._indexes(removed, "certifications"))
        pruned.education = self._drop_indexes(pruned.education, self._indexes(removed, "education"))
        for item_index, entry in enumerate(pruned.experiences):
            entry.bullets = self._drop_indexes(entry.bullets, self._bullet_indexes(removed, "experience", item_index))
        for item_index, project in enumerate(pruned.projects):
            project.bullets = self._drop_indexes(project.bullets, self._bullet_indexes(removed, "projects", item_index))
        pruned.projects = [project for project in pruned.projects if project.bullets]
        return pruned

    def _prune_summary(self, cv: TailoredCv, removed: list[CvClaim]) -> str | None:
        sentences = self._drop_indexes(self._extractor.summary_sentences(cv), self._indexes(removed, "summary"))
        return " ".join(sentences) or None

    @staticmethod
    def _indexes(claims: list[CvClaim], section: str) -> set[int]:
        return {claim.item_index for claim in claims if claim.section == section and claim.item_index is not None}

    @staticmethod
    def _bullet_indexes(claims: list[CvClaim], section: str, item_index: int) -> set[int]:
        return {claim.bullet_index for claim in claims if claim.section == section and claim.item_index == item_index and claim.bullet_index is not None}

    @staticmethod
    def _drop_indexes(items: list, indexes: set[int]) -> list:
        return [item for index, item in enumerate(items) if index not in indexes]
