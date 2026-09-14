"""Consistent error envelope + error codes shared across the whole API."""
from enum import StrEnum


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_BAD_RESPONSE = "LLM_BAD_RESPONSE"
    LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_INVALID_OUTPUT = "LLM_INVALID_OUTPUT"
    NOT_FOUND = "NOT_FOUND"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Base class for every error we turn into the standard JSON envelope."""

    status_code = 500
    code = ErrorCode.INTERNAL_ERROR
    message = "An unexpected error occurred."

    def __init__(self, message: str | None = None, *, code: ErrorCode | None = None,
                 status_code: int | None = None) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        super().__init__(self.message)


class InvalidRequestError(AppError):
    status_code = 400
    code = ErrorCode.INVALID_REQUEST


class NotFoundError(AppError):
    status_code = 404
    code = ErrorCode.NOT_FOUND


class DatabaseError(AppError):
    status_code = 500
    code = ErrorCode.DATABASE_ERROR


class LLMError(AppError):
    """Anything that went wrong talking to / parsing from the LLM."""


class LLMNotConfiguredError(LLMError):
    status_code = 503
    code = ErrorCode.LLM_NOT_CONFIGURED
    message = "LLM is not configured (missing OPENAI_API_KEY)."


class LLMTimeoutError(LLMError):
    status_code = 504
    code = ErrorCode.LLM_TIMEOUT
    message = "The LLM did not respond in time. Please retry."


class LLMRateLimitError(LLMError):
    status_code = 429
    code = ErrorCode.LLM_RATE_LIMIT
    message = "The LLM provider is rate limiting us. Please retry shortly."


class LLMUnavailableError(LLMError):
    status_code = 503
    code = ErrorCode.LLM_UNAVAILABLE
    message = "The LLM provider is unreachable right now. Please retry."


class LLMBadResponseError(LLMError):
    status_code = 502
    code = ErrorCode.LLM_BAD_RESPONSE
    message = "The LLM returned an unusable response. Please retry."


class LLMInvalidOutputError(LLMError):
    status_code = 502
    code = ErrorCode.LLM_INVALID_OUTPUT
    message = "The LLM returned malformed or incomplete JSON. Please retry."
