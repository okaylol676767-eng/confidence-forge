"""Attachment upload tests: multipart happy paths, validation rejects, Gemini parts."""
import base64
import json

import pytest

from app.attachments import Attachment, validate_attachments, LIMITS
from app.errors import InvalidRequestError


# ---------- unit: validation ----------

def _png(name: str = "pic.png", fill: bytes = b"\x89PNG-fake-image-bytes") -> tuple:
    return name, "image/png", fill


class _FakeUpload:
    def __init__(self, filename: str, content_type: str, data: bytes):
        self.filename = filename
        self.content_type = content_type
        self.size = len(data)
        import io
        self.file = io.BytesIO(data)


def test_validate_accepts_image():
    name, mime, data = _png()
    uploads = [_FakeUpload(name, mime, data)]
    result = validate_attachments(uploads)
    assert len(result) == 1
    assert result[0].is_image
    assert result[0].mime_type == "image/png"
    assert result[0].data == data


def test_validate_accepts_pdf_and_text():
    uploads = [
        _FakeUpload("report.pdf", "application/pdf", b"%PDF-1.4 fake"),
        _FakeUpload("notes.txt", "text/plain", "hello notes".encode()),
        _FakeUpload("data.csv", "text/csv", b"a,b,c\n1,2,3"),
    ]
    result = validate_attachments(uploads)
    assert [a.mime_type for a in result] == [
        "application/pdf", "text/plain", "text/csv",
    ]


def test_validate_rejects_unsupported_type():
    with pytest.raises(InvalidRequestError) as exc:
        validate_attachments([_FakeUpload("evil.exe", "application/octet-stream", b"MZ")])
    assert "Unsupported file type" in exc.value.message


def test_validate_rejects_oversized_file():
    big = b"x" * (LIMITS.max_bytes_per_file + 1)
    with pytest.raises(InvalidRequestError) as exc:
        validate_attachments([_FakeUpload("big.png", "image/png", big)])
    assert "too large" in exc.value.message


def test_validate_rejects_empty_file():
    with pytest.raises(InvalidRequestError) as exc:
        validate_attachments([_FakeUpload("empty.png", "image/png", b"")])
    assert "empty" in exc.value.message


def test_validate_rejects_too_many_files():
    name, mime, data = _png()
    uploads = [_FakeUpload(f"{name}", mime, data) for _ in range(LIMITS.max_files + 1)]
    with pytest.raises(InvalidRequestError) as exc:
        validate_attachments(uploads)
    assert "Too many attachments" in exc.value.message


# ---------- unit: Gemini inline parts ----------

def test_gemini_build_content_with_attachments():
    from app.llm_gemini import GeminiClient

    image = Attachment(filename="a.png", mime_type="image/png", data=b"img")
    pdf = Attachment(filename="b.pdf", mime_type="application/pdf", data=b"pdf")
    parts = GeminiClient._build_content("What is this?", [image, pdf])
    assert isinstance(parts, list)
    assert parts[0]["inline_data"]["mime_type"] == "image/png"
    assert base64.b64decode(parts[0]["inline_data"]["data"]) == b"img"
    assert parts[1]["inline_data"]["mime_type"] == "application/pdf"
    assert parts[-1] == "What is this?"  # prompt goes last


def test_gemini_build_content_without_attachments_is_plain_string():
    from app.llm_gemini import GeminiClient

    content = GeminiClient._build_content("hello", None)
    assert content == "hello"


# ---------- integration: POST /chat with multipart ----------

GOOD_JSON = json.dumps({
    "answer": "The image shows a red square.",
    "confidence": 0.92,
    "confidence_reason": "Clear image content.",
    "uncertainty_factors": [],
})


def test_multipart_chat_with_image(client, fake_llm):
    fake_llm.response = GOOD_JSON
    fake_llm.answer = "The image shows a red square."
    fake_llm.confidence = 0.92
    data = {"message": "What do you see?"}
    files = [("files", ("square.png", b"\x89PNG-fake", "image/png"))]
    res = client.post("/chat", data=data, files=files)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["answer"].startswith("The image shows")
    assert body["confidence"] == 0.92
    assert body["attachments"] == [
        {"filename": "square.png", "mime_type": "image/png",
         "size_bytes": len(b"\x89PNG-fake"), "kind": "image"}
    ]
    assert fake_llm.attachment_calls  # attachments reached the LLM call


def test_multipart_chat_pdf_document(client, fake_llm):
    fake_llm.response = GOOD_JSON
    res = client.post(
        "/chat",
        data={"message": "Summarize the PDF"},
        files=[("files", ("doc.pdf", b"%PDF-1.4 x", "application/pdf"))],
    )
    assert res.status_code == 200
    assert res.json()["attachments"][0]["kind"] == "document"


def test_multipart_chat_rejects_bad_type(client, fake_llm):
    res = client.post(
        "/chat",
        data={"message": "hello"},
        files=[("files", ("virus.exe", b"MZ", "application/octet-stream"))],
    )
    assert res.status_code == 400
    body = res.json()
    assert body["error"] is True
    assert body["code"] == "INVALID_REQUEST"


def test_multipart_attachment_only_send_gets_default_prompt(client, fake_llm):
    """Dropping a file with no text is valid: the backend supplies a prompt."""
    res = client.post(
        "/chat",
        data={"message": ""},
        files=[("files", ("a.png", b"x", "image/png"))],
    )
    assert res.status_code == 200, res.text
    # The default prompt references the attached filename.
    assert "a.png" in fake_llm.calls[-1][-1]["content"]


def test_form_encoded_body_without_files_is_rejected(client, fake_llm):
    """A urlencoded body (no files) is not valid JSON -> 400 envelope."""
    res = client.post("/chat", data={"message": ""})
    assert res.status_code == 400
    body = res.json()
    assert body["error"] is True
    assert body["code"] == "INVALID_REQUEST"


def test_json_body_still_works(client, fake_llm):
    """The original JSON contract must remain untouched."""
    res = client.post("/chat", json={"message": "hi"})
    assert res.status_code == 200
    assert res.json()["attachments"] == []
