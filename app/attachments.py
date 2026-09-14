"""Shared attachment validation used by the multipart chat route.

Pure functions, no I/O — the router hands UploadFile objects here for policy
checks before anything touches the LLM or the database.
"""
import mimetypes
from dataclasses import dataclass

from fastapi import UploadFile

from .errors import InvalidRequestError

# Content types Gemini accepts inline (images, PDF, plain text).
ALLOWED_MIME_PREFIXES = ("image/",)
ALLOWED_MIME_EXACT = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
}


@dataclass(frozen=True)
class AttachmentLimits:
    """Upload policy. Enforced before reading whole files into memory."""

    max_files: int = 4
    max_bytes_per_file: int = 8 * 1024 * 1024   # 8 MB
    max_total_bytes: int = 16 * 1024 * 1024     # 16 MB across all files


LIMITS = AttachmentLimits()


@dataclass(frozen=True)
class Attachment:
    """A validated, in-memory attachment ready for the LLM call."""

    filename: str
    mime_type: str
    data: bytes

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")


def allowed_mime(filename: str, declared: str | None) -> str | None:
    """Resolve the effective MIME type: browser-declared first, filename guess fallback.

    The declared type wins because some OSes (notably Windows) return quirky
    registry-based guesses from mimetypes.guess_type for common extensions.
    """
    candidates: list[str] = []
    if declared:
        candidates.append(declared.split(";")[0].strip().lower())
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        candidates.append(guessed.strip().lower())
    for mime in candidates:
        if mime and (mime in ALLOWED_MIME_EXACT or any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES)):
            return mime
    return None


def validate_attachments(uploads: list[UploadFile]) -> list[Attachment]:
    """Validate a batch of uploads into in-memory Attachments.

    Raises InvalidRequestError (400 envelope) with a precise message when any
    rule is violated: count, unknown/unsupported type, per-file size, or
    total size. Empty content is rejected too — Gemini rejects empty parts.
    """
    if not uploads:
        return []
    if len(uploads) > LIMITS.max_files:
        raise InvalidRequestError(
            f"Too many attachments: {len(uploads)} (max {LIMITS.max_files})."
        )

    attachments: list[Attachment] = []
    total = 0
    for upload in uploads:
        filename = upload.filename or "attachment"
        mime = allowed_mime(filename, upload.content_type)
        if mime is None:
            raise InvalidRequestError(
                f"Unsupported file type for '{filename}'. "
                "Accepted: images (png/jpg/webp/heic/heif), PDF, txt, md, csv, json."
            )
        # Size guard BEFORE reading: cheap early rejection for huge uploads.
        declared_size = upload.size
        if declared_size is not None and declared_size > LIMITS.max_bytes_per_file:
            raise InvalidRequestError(
                f"'{filename}' is too large (max {LIMITS.max_bytes_per_file // (1024 * 1024)} MB)."
            )
        data = upload.file.read()
        if len(data) > LIMITS.max_bytes_per_file:
            raise InvalidRequestError(
                f"'{filename}' is too large (max {LIMITS.max_bytes_per_file // (1024 * 1024)} MB)."
            )
        if not data:
            raise InvalidRequestError(f"'{filename}' is empty.")
        total += len(data)
        if total > LIMITS.max_total_bytes:
            raise InvalidRequestError(
                f"Attachments are too large in total (max {LIMITS.max_total_bytes // (1024 * 1024)} MB)."
            )
        attachments.append(Attachment(filename=filename, mime_type=mime, data=data))
    return attachments
