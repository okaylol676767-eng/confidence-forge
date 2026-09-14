"""Shared attachment validation used by the multipart chat route.

Pure functions, no I/O — the router hands UploadFile objects here for policy
checks before anything touches the LLM or the database.
"""
import io
import logging
import mimetypes
from dataclasses import dataclass, field

from fastapi import UploadFile

from .errors import InvalidRequestError

logger = logging.getLogger("confidence_forge.attachments")

# Content types Gemini accepts inline (images, PDF, plain text).
ALLOWED_MIME_PREFIXES = ("image/",)
ALLOWED_MIME_EXACT = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
}

# Cap on server-extracted PDF text: bounds prompt size / token cost.
MAX_PDF_TEXT_CHARS = 60_000


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
    # Server-side text extraction for PDFs (None when unavailable). Sent to
    # the LLM alongside the binary: Gemini's native PDF parsing is unreliable
    # on real-world compressed streams, so the text layer is the guarantee.
    extracted_text: str | None = field(default=None)

    @property
    def is_image(self) -> bool:
        return self.mime_type.startswith("image/")


def extract_pdf_text(data: bytes, filename: str = "document.pdf") -> str | None:
    """Extract the text layer of a PDF with pypdf; None when it fails.

    Never raises: an unreadable PDF is not an invalid upload (Gemini may
    still parse it natively), it just gets no text fallback.
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text.strip())
        if not pages:
            return None
        joined = "\n\n".join(pages)
        if len(joined) > MAX_PDF_TEXT_CHARS:
            joined = joined[:MAX_PDF_TEXT_CHARS] + "\n…[truncated]"
        return joined
    except Exception as exc:  # pypdf errors, corrupt/truncated/encrypted files
        logger.warning(
            "PDF text extraction failed for '%s': %s: %s",
            filename, type(exc).__name__, str(exc)[:200],
        )
        return None


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
        extracted_text = (
            extract_pdf_text(data, filename)
            if mime == "application/pdf"
            else None
        )
        if mime == "application/pdf":
            logger.info(
                "pdf text extraction filename=%s chars=%s",
                filename, len(extracted_text) if extracted_text else 0,
            )
        attachments.append(
            Attachment(filename=filename, mime_type=mime, data=data, extracted_text=extracted_text)
        )
    return attachments
