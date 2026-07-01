"""Tests for failed document tracking."""

from main import _apply_suggestions
from paperless.models import CategorizationSuggestion


class CapturingPaperless:
    """Paperless stub that records document updates."""

    def __init__(self):
        self.updates: list[dict] = []

    def update_document(self, **kwargs):
        self.updates.append(kwargs)


class FailedTagEngine:
    """Engine stub with deterministic tracking tag IDs."""

    def __init__(self):
        self.paperless = CapturingPaperless()
        self.parsed_tag_requests = 0
        self.failed_tag_requests = 0

    def get_or_create_parsed_tag(self) -> int:
        self.parsed_tag_requests += 1
        return 20

    def get_or_create_failed_tag(self) -> int:
        self.failed_tag_requests += 1
        return 30

    def has_unresolved_new_correspondent(self, suggestion) -> bool:
        del suggestion
        return False

    def processing_custom_field_values(self, metadata):
        del metadata
        return []


def test_apply_suggestions_tags_error_documents_as_failed():
    engine = FailedTagEngine()
    suggestion = CategorizationSuggestion(
        document_id=42,
        current_title="scan.pdf",
        current_tags=[10],
        status="error",
        error_message="Document has no OCR content or supported attachment",
    )

    _apply_suggestions(engine, [suggestion])

    assert engine.paperless.updates == [
        {
            "document_id": 42,
            "tags": [10, 30],
        }
    ]
    assert engine.parsed_tag_requests == 0
    assert engine.failed_tag_requests == 1
