from enum import StrEnum

class JobSourceType(StrEnum):
    URL = "url"
    TEXT = "text"

class IngestionStatus(StrEnum):
    OK = "ok"
    NEEDS_MANUAL_PASTE = "needs_manual_paste"
    FAILED = "failed"

class DocumentKind(StrEnum):
    CV = "cv"
    EXTRA = "extra"

class RequirementPriority(StrEnum):
    MUST_HAVE = "must_have"
    NICE_TO_HAVE = "nice_to_have"

class RequirementVerdict(StrEnum):
    MET = "met"
    PARTIAL = "partial"
    MISSING = "missing"

class FitDimension(StrEnum):
    TECHNICAL = "technical"
    DOMAIN = "domain"
    TOOLS = "tools"
    SOFT_SKILLS = "soft_skills"

class SeniorityMatch(StrEnum):
    BELOW = "below"
    MATCHES = "matches"
    ABOVE = "above"

class RiskSide(StrEnum):
    JOB = "job"
    CANDIDATE = "candidate"

class Recommendation(StrEnum):
    APPLY = "apply"
    APPLY_AFTER_TAILORING = "apply_after_tailoring"
    SKIP = "skip"

class AnalysisStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class JobAnalysisStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    SKIPPED = "skipped"

class AgentStatus(StrEnum):
    RUNNING = "running"
    FINALIZED = "finalized"
    FAILED = "failed"

class ExportFormat(StrEnum):
    DOCX = "docx"
    PDF = "pdf"
    MD = "md"

class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
