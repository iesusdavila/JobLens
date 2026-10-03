from typing import Any

class AppError(Exception):
    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

class ConfigurationError(AppError):
    status_code = 500
    error_code = "configuration_error"

class SessionNotFoundError(AppError):
    status_code = 404
    error_code = "session_not_found"

class JobNotFoundError(AppError):
    status_code = 404
    error_code = "job_not_found"

class DocumentParsingError(AppError):
    status_code = 422
    error_code = "document_parsing_failed"

class UnsupportedFileTypeError(AppError):
    status_code = 415
    error_code = "unsupported_file_type"

class FileTooLargeError(AppError):
    status_code = 413
    error_code = "file_too_large"

class InvalidJobInputError(AppError):
    status_code = 422
    error_code = "invalid_job_input"

class TooManyJobsError(AppError):
    status_code = 422
    error_code = "too_many_jobs"

class MissingPrerequisiteError(AppError):
    status_code = 409
    error_code = "missing_prerequisite"

class AnalysisInProgressError(AppError):
    status_code = 409
    error_code = "analysis_in_progress"

class AnalysisNotReadyError(AppError):
    status_code = 409
    error_code = "analysis_not_ready"

class ExportNotAvailableError(AppError):
    status_code = 404
    error_code = "export_not_available"

class JevServiceError(AppError):
    status_code = 502
    error_code = "jev_unavailable"

class JevStateTooLargeError(AppError):
    status_code = 422
    error_code = "jev_state_too_large"

class LlmServiceError(AppError):
    status_code = 502
    error_code = "llm_unavailable"

class LlmOutputError(AppError):
    status_code = 502
    error_code = "llm_output_invalid"

class ChatError(AppError):
    status_code = 502
    error_code = "chat_failed"

class InvalidRequestError(AppError):
    status_code = 422
    error_code = "invalid_request"
