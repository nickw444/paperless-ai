"""Tests for Paperless document attachment downloads."""

from datetime import datetime
from pathlib import Path

from paperless.client import PaperlessClient
from paperless.models import Document


class FakeResponse:
    """Small response double for streamed downloads."""

    def __init__(self, *, headers: dict[str, str], chunks: list[bytes], status_code: int = 200):
        self.headers = headers
        self._chunks = chunks
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import HTTPError

            error = HTTPError("failed")
            error.response = self
            raise error

    def iter_content(self, chunk_size: int):
        del chunk_size
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeSession:
    """Session double that returns queued responses and records requests."""

    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.requests: list[tuple[str, dict | None]] = []
        self.headers = {}

    def mount(self, *args, **kwargs):
        del args, kwargs

    def get(self, url, params=None, timeout=None, stream=False):
        del timeout, stream
        self.requests.append((url, params))
        return self.responses.pop(0)


def _document(*, mime_type: str | None, original_file_name: str = "scan.pdf") -> Document:
    return Document(
        id=42,
        title="scan",
        content="OCR",
        tags=[],
        created=datetime(2024, 1, 1),
        created_date="2024-01-01",
        modified=datetime(2024, 1, 1),
        added=datetime(2024, 1, 1),
        original_file_name=original_file_name,
        archived_file_name="scan-archived.pdf",
        mime_type=mime_type,
    )


def _client(session: FakeSession) -> PaperlessClient:
    client = PaperlessClient()
    client.session = session
    return client


def test_supported_original_pdf_uses_original_download():
    session = FakeSession(
        [
            FakeResponse(
                headers={
                    "content-type": "application/pdf",
                    "content-disposition": 'attachment; filename="scan.pdf"',
                    "content-length": "12",
                },
                chunks=[b"%PDF content"],
            )
        ]
    )

    attachment = _client(session).download_document_attachment(
        _document(mime_type="application/pdf")
    )

    assert attachment is not None
    assert attachment.source == "original"
    assert attachment.mime_type == "application/pdf"
    assert attachment.filename == "scan.pdf"
    assert Path(attachment.path).read_bytes() == b"%PDF content"
    assert session.requests[0][1] == {"original": "true"}
    Path(attachment.path).unlink()


def test_unknown_original_mime_type_uses_original_when_response_is_supported():
    session = FakeSession(
        [
            FakeResponse(
                headers={"content-type": "image/png", "content-length": "7"},
                chunks=[b"pngdata"],
            )
        ]
    )

    attachment = _client(session).download_document_attachment(_document(mime_type=None))

    assert attachment is not None
    assert attachment.source == "original"
    assert attachment.mime_type == "image/png"
    assert session.requests[0][1] == {"original": "true"}
    Path(attachment.path).unlink()


def test_unsupported_original_mime_type_falls_back_to_archived_pdf():
    session = FakeSession(
        [
            FakeResponse(
                headers={
                    "content-type": "application/pdf",
                    "content-disposition": 'attachment; filename="scan-archived.pdf"',
                    "content-length": "12",
                },
                chunks=[b"%PDF archive"],
            )
        ]
    )

    attachment = _client(session).download_document_attachment(
        _document(mime_type="message/rfc822", original_file_name="message.eml")
    )

    assert attachment is not None
    assert attachment.source == "archived"
    assert attachment.filename == "scan-archived.pdf"
    assert session.requests[0][1] is None
    Path(attachment.path).unlink()


def test_unsupported_original_and_archived_returns_none():
    session = FakeSession(
        [
            FakeResponse(
                headers={"content-type": "text/plain", "content-length": "4"},
                chunks=[b"text"],
            )
        ]
    )

    attachment = _client(session).download_document_attachment(
        _document(mime_type="message/rfc822", original_file_name="message.eml")
    )

    assert attachment is None


def test_oversized_attachment_returns_none_without_download():
    session = FakeSession(
        [
            FakeResponse(
                headers={
                    "content-type": "application/pdf",
                    "content-length": str(20_000_001),
                },
                chunks=[b"%PDF content"],
            ),
            FakeResponse(
                headers={"content-type": "application/json"},
                chunks=[],
                status_code=404,
            ),
        ]
    )

    attachment = _client(session).download_document_attachment(
        _document(mime_type="application/pdf")
    )

    assert attachment is None
    assert len(session.requests) == 2
