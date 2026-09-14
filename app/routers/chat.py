"""POST /chat — the main chat endpoint (JSON body or multipart with attachments)."""
from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..attachments import validate_attachments
from ..database import get_session
from ..errors import InvalidRequestError
from ..schemas import ChatRequest, ChatResponse
from ..services import handle_chat

router = APIRouter(tags=["chat"])


def _chat_payload_from_form(form, attachments: list) -> ChatRequest:
    """Build the validated ChatRequest from multipart fields.

    Attachment-only sends (no text) get a sensible default prompt so users
    can just drop in an image and ask "what is this?" without typing.
    """
    raw_id = form.get("conversation_id")
    conversation_id = str(raw_id).strip() if raw_id else None
    message = str(form.get("message", "")).strip()
    if not message and attachments:
        described = ", ".join(a.filename for a in attachments)
        message = f"Please analyze the attached file(s): {described}."
    try:
        return ChatRequest(
            message=message,
            conversation_id=conversation_id or None,
        )
    except ValidationError as exc:
        # Reuse the standard 422 VALIDATION_ERROR path/wording.
        raise RequestValidationError(exc.errors()) from None


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, session: AsyncSession = Depends(get_session)) -> ChatResponse:
    content_type = request.headers.get("content-type", "").lower()

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        uploads = [
            item
            for item in (*form.getlist("files"), *form.getlist("file"))
            if hasattr(item, "file") or hasattr(item, "read")
        ]
        attachments = validate_attachments(uploads)  # 400 envelope on bad uploads
        payload = _chat_payload_from_form(form, attachments)
        return await handle_chat(session, payload, attachments=attachments)

    # Plain JSON body (the original contract).
    try:
        body = await request.json()
    except Exception as exc:
        raise InvalidRequestError("Request body must be valid JSON.") from exc
    if not isinstance(body, dict):
        raise InvalidRequestError("Request body must be a JSON object.")
    try:
        payload = ChatRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from None
    return await handle_chat(session, payload)
