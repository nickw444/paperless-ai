"""Tests for Paperless API payload construction."""

from datetime import datetime

from paperless.client import PaperlessClient


class CapturingPaperlessClient(PaperlessClient):
    """Paperless client that captures PATCH payloads without network access."""

    def __init__(self):
        self.patch_calls: list[tuple[str, dict]] = []

    def _patch(self, endpoint: str, data: dict) -> dict:
        self.patch_calls.append((endpoint, data))
        return {
            "id": 42,
            "title": data.get("title", "scan.pdf"),
            "content": data.get("content", ""),
            "correspondent": data.get("correspondent"),
            "document_type": data.get("document_type"),
            "storage_path": data.get("storage_path"),
            "tags": data.get("tags", []),
            "created": datetime(2024, 1, 1).isoformat(),
            "created_date": "2024-01-01",
            "modified": datetime(2024, 1, 1).isoformat(),
            "added": datetime(2024, 1, 1).isoformat(),
            "original_file_name": "scan.pdf",
        }


def test_update_document_includes_content_when_provided():
    client = CapturingPaperlessClient()

    document = client.update_document(
        document_id=42,
        title="Invoice",
        content="Invoice\nTotal $42",
        tags=[1, 2],
    )

    assert client.patch_calls == [
        (
            "/api/documents/42/",
            {
                "title": "Invoice",
                "content": "Invoice\nTotal $42",
                "tags": [1, 2],
            },
        )
    ]
    assert document.content == "Invoice\nTotal $42"


class ListingPaperlessClient(PaperlessClient):
    """Paperless client that returns canned paginated document payloads."""

    def __init__(self):
        self.documents = [
            {
                "id": 1,
                "title": "unprocessed.pdf",
                "content": "",
                "tags": [10],
                "created": datetime(2024, 1, 1).isoformat(),
                "created_date": "2024-01-01",
                "modified": datetime(2024, 1, 1).isoformat(),
                "added": datetime(2024, 1, 1).isoformat(),
                "original_file_name": "unprocessed.pdf",
            },
            {
                "id": 2,
                "title": "parsed.pdf",
                "content": "",
                "tags": [10, 20],
                "created": datetime(2024, 1, 1).isoformat(),
                "created_date": "2024-01-01",
                "modified": datetime(2024, 1, 1).isoformat(),
                "added": datetime(2024, 1, 1).isoformat(),
                "original_file_name": "parsed.pdf",
            },
            {
                "id": 3,
                "title": "failed.pdf",
                "content": "",
                "tags": [10, 30],
                "created": datetime(2024, 1, 1).isoformat(),
                "created_date": "2024-01-01",
                "modified": datetime(2024, 1, 1).isoformat(),
                "added": datetime(2024, 1, 1).isoformat(),
                "original_file_name": "failed.pdf",
            },
        ]

    def _get_all_pages(self, endpoint: str, params: dict | None = None) -> list[dict]:
        assert endpoint == "/api/documents/"
        assert params == {"is_in_inbox": "true"}
        return self.documents


def test_list_inbox_documents_excludes_any_requested_tag():
    client = ListingPaperlessClient()

    documents = client.list_inbox_documents(exclude_tag_ids=[20, 30])

    assert [document.id for document in documents] == [1]
