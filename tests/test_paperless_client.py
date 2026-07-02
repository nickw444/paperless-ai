"""Tests for Paperless API payload construction."""

from datetime import datetime

from paperless.client import PaperlessClient


class CapturingPaperlessClient(PaperlessClient):
    """Paperless client that captures request payloads without network access."""

    def __init__(self):
        self.patch_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []
        self.page_results: dict[str, list[dict]] = {}

    def _post(self, endpoint: str, data: dict) -> dict:
        self.post_calls.append((endpoint, data))
        if endpoint == "/api/correspondents/":
            return {
                "id": 7,
                "name": data["name"],
                "slug": data["name"].lower().replace(" ", "-"),
                "match": data.get("match", ""),
                "matching_algorithm": data.get("matching_algorithm", 0),
            }
        if endpoint == "/api/custom_fields/":
            return {
                "id": 99,
                "name": data["name"],
                "data_type": data["data_type"],
                "extra_data": {},
            }
        return {
            "id": 99,
            "name": data.get("name", ""),
        }

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

    def _get_all_pages(self, endpoint: str, params: dict | None = None) -> list[dict]:
        del params
        return self.page_results.get(endpoint, [])


def test_update_document_includes_content_when_provided():
    client = CapturingPaperlessClient()

    document = client.update_document(
        document_id=42,
        title="Invoice",
        content="Invoice\nTotal $42",
        created="2024-01-15",
        tags=[1, 2],
    )

    assert client.patch_calls == [
        (
            "/api/documents/42/",
            {
                "title": "Invoice",
                "content": "Invoice\nTotal $42",
                "created": "2024-01-15",
                "tags": [1, 2],
            },
        )
    ]
    assert document.content == "Invoice\nTotal $42"


def test_create_correspondent_disables_automatic_matching():
    client = CapturingPaperlessClient()

    correspondent = client.create_correspondent("Acme Corp")

    assert client.post_calls == [
        (
            "/api/correspondents/",
            {
                "name": "Acme Corp",
                "matching_algorithm": 0,
            },
        )
    ]
    assert correspondent.matching_algorithm == 0


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


def test_update_document_includes_custom_fields_when_provided():
    client = CapturingPaperlessClient()

    client.update_document(
        document_id=42,
        title="Invoice",
        custom_fields=[
            {"field": 7, "value": "1"},
            {"field": 8, "value": "gpt-5"},
            {"field": 9, "value": '{"total":100}'},
        ],
    )

    assert client.patch_calls == [
        (
            "/api/documents/42/",
            {
                "title": "Invoice",
                "custom_fields": [
                    {"field": 7, "value": "1"},
                    {"field": 8, "value": "gpt-5"},
                    {"field": 9, "value": '{"total":100}'},
                ],
            },
        )
    ]


def test_list_and_create_custom_fields():
    client = CapturingPaperlessClient()
    client.page_results["/api/custom_fields/"] = [
        {"id": 7, "name": "paperless-ai-version", "data_type": "string", "extra_data": None}
    ]

    fields = client.list_custom_fields()
    created = client.create_custom_field("paperless-ai-model")

    assert fields[0].id == 7
    assert fields[0].name == "paperless-ai-version"
    assert fields[0].extra_data == {}
    assert client.post_calls == [
        ("/api/custom_fields/", {"name": "paperless-ai-model", "data_type": "string"})
    ]
    assert created.name == "paperless-ai-model"
