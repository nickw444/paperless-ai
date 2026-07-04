"""Tests for paperless-ai processing metadata custom fields."""

from datetime import datetime

from categorizer.engine import CategorizationEngine, _format_token_metadata_json
from config.settings import settings
from llm.schemas import AgentCategorizationResult
from llm.usage import AgentUsageMetadata
from main import (
    _apply_suggestions,
    _should_analyze_for_stale_reprocessing,
)
from paperless.models import (
    CategorizationSuggestion,
    CustomField,
    Document,
    ProcessingMetadata,
    Tag,
)


class StubAgent:
    def categorize_document(self, *args, **kwargs):
        del args, kwargs
        return AgentCategorizationResult()


class CapturingPaperless:
    def __init__(self):
        self.updated_documents: list[dict] = []
        self.created_custom_fields: list[tuple[str, str]] = []
        self.custom_fields: list[CustomField] = []

    def list_tags(self):
        return [
            Tag(id=3, name="paperless-ai-parsed", slug="paperless-ai-parsed"),
            Tag(id=4, name="paperless-ai-failed", slug="paperless-ai-failed"),
        ]

    def list_correspondents(self):
        return []

    def list_document_types(self):
        return []

    def list_storage_paths(self):
        return []

    def list_custom_fields(self):
        return self.custom_fields

    def create_custom_field(self, name: str, data_type: str = "string"):
        field = CustomField(id=len(self.custom_fields) + 10, name=name, data_type=data_type)
        self.created_custom_fields.append((name, data_type))
        return field

    def update_document(self, **kwargs):
        self.updated_documents.append(kwargs)
        return _make_document()


class ExistingAfterCreateConflictPaperless(CapturingPaperless):
    def __init__(self):
        super().__init__()
        self.custom_fields = [
            CustomField(id=10, name="paperless-ai-version"),
            CustomField(id=11, name="paperless-ai-model"),
            CustomField(id=12, name="paperless-ai-tokens"),
        ]

    def list_custom_fields(self):
        return [] if self.created_custom_fields == [] else self.custom_fields

    def create_custom_field(self, name: str, data_type: str = "string"):
        self.created_custom_fields.append((name, data_type))
        raise ValueError('Bad request: {"name":["custom field with this name already exists."]}')


def _make_document(*, tags: list[int] | None = None, custom_fields=None) -> Document:
    return Document(
        id=42,
        title="scan.pdf",
        content="Invoice",
        tags=tags or [],
        custom_fields=custom_fields or [],
        created=datetime(2024, 1, 1),
        created_date="2024-01-01",
        modified=datetime(2024, 1, 1),
        added=datetime(2024, 1, 1),
        original_file_name="scan.pdf",
    )


def _successful_suggestion() -> CategorizationSuggestion:
    return CategorizationSuggestion(
        document_id=42,
        current_title="scan.pdf",
        suggested_title="Invoice",
        suggested_tag_ids=[1, 2],
        status="success",
        processing_metadata=ProcessingMetadata(
            version="1",
            model="gpt-5",
            tokens='{"total":123,"input":100,"output":23}',
        ),
    )


def test_token_metadata_json_omits_missing_values():
    usage = AgentUsageMetadata(total_tokens=123, output_tokens=23)

    assert _format_token_metadata_json(usage) == '{"total":123,"output":23}'
    assert _format_token_metadata_json(AgentUsageMetadata()) is None


def test_processing_metadata_uses_configured_model_when_usage_has_no_model():
    engine = CategorizationEngine(agent=StubAgent())

    metadata = engine.processing_metadata_for_result(AgentCategorizationResult())

    assert metadata.version == settings.processing.backfill_comparison_version
    assert metadata.model == settings.codex.model
    assert metadata.tokens is None


def test_apply_auto_creates_processing_fields_and_writes_metadata():
    engine = CategorizationEngine(agent=StubAgent())
    paperless = CapturingPaperless()
    engine.paperless = paperless
    engine._tags = paperless.list_tags()

    _apply_suggestions(engine, [_successful_suggestion()])

    assert paperless.created_custom_fields == [
        ("paperless-ai-version", "string"),
        ("paperless-ai-model", "string"),
        ("paperless-ai-tokens", "string"),
    ]
    assert paperless.updated_documents[0]["custom_fields"] == [
        {"field": 10, "value": "1"},
        {"field": 11, "value": "gpt-5"},
        {"field": 12, "value": '{"total":123,"input":100,"output":23}'},
    ]
    assert paperless.updated_documents[0]["tags"] == [1, 2, 3]


def test_apply_writes_suggested_document_date_as_created():
    engine = CategorizationEngine(agent=StubAgent())
    paperless = CapturingPaperless()
    engine.paperless = paperless
    engine._tags = paperless.list_tags()
    suggestion = _successful_suggestion()
    suggestion.suggested_document_date = "2024-01-15"

    _apply_suggestions(engine, [suggestion])

    assert paperless.updated_documents[0]["created"] == "2024-01-15"


def test_processing_fields_reload_when_create_reports_existing_name():
    engine = CategorizationEngine(agent=StubAgent())
    paperless = ExistingAfterCreateConflictPaperless()
    engine.paperless = paperless

    values = engine.processing_custom_field_values(_successful_suggestion().processing_metadata)

    assert values == [
        {"field": 10, "value": "1"},
        {"field": 11, "value": "gpt-5"},
        {"field": 12, "value": '{"total":123,"input":100,"output":23}'},
    ]
    assert paperless.created_custom_fields == [("paperless-ai-version", "string")]


def test_apply_tags_pre_agent_failed_suggestions_without_processing_metadata():
    engine = CategorizationEngine(agent=StubAgent())
    paperless = CapturingPaperless()
    engine.paperless = paperless
    engine._tags = paperless.list_tags()
    suggestion = CategorizationSuggestion(
        document_id=42,
        current_title="scan.pdf",
        current_tags=[],
        status="error",
        error_message="Document has no OCR content or supported attachment",
    )

    _apply_suggestions(engine, [suggestion])

    assert paperless.updated_documents == [{"document_id": 42, "tags": [4]}]
    assert paperless.created_custom_fields == []


def test_apply_tags_post_agent_failed_suggestions_with_processing_metadata():
    engine = CategorizationEngine(agent=StubAgent())
    paperless = CapturingPaperless()
    engine.paperless = paperless
    engine._tags = paperless.list_tags()
    suggestion = _successful_suggestion()
    suggestion.status = "error"
    suggestion.current_tags = [1]
    suggestion.error_message = "Document attachment did not provide usable OCR content"

    _apply_suggestions(engine, [suggestion])

    assert paperless.updated_documents == [
        {
            "document_id": 42,
            "tags": [1, 4],
            "custom_fields": [
                {"field": 10, "value": "1"},
                {"field": 11, "value": "gpt-5"},
                {"field": 12, "value": '{"total":123,"input":100,"output":23}'},
            ],
        }
    ]


def test_stale_reprocessing_filter_uses_version_field_only():
    engine = CategorizationEngine(agent=StubAgent())
    parsed_tag_id = 3
    version_field_id = 10

    unparsed = _make_document(tags=[])
    current = _make_document(
        tags=[parsed_tag_id],
        custom_fields=[{"field": 10, "value": settings.processing.backfill_comparison_version}],
    )
    stale = _make_document(tags=[parsed_tag_id], custom_fields=[{"field": 10, "value": "0"}])

    assert _should_analyze_for_stale_reprocessing(engine, unparsed, parsed_tag_id, version_field_id)
    assert not _should_analyze_for_stale_reprocessing(
        engine, current, parsed_tag_id, version_field_id
    )
    assert _should_analyze_for_stale_reprocessing(engine, stale, parsed_tag_id, version_field_id)
