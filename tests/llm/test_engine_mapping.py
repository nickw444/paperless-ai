"""Tests for mapping agent JSON output through the categorization engine."""

from datetime import datetime

from categorizer.engine import FAILED_TAG_NAME, PARSED_TAG_NAME, CategorizationEngine
from llm.schemas import (
    AgentCategorizationResult,
    AvailableOptions,
    CategorizationAgentOutput,
    CurrentMetadata,
    EntityOption,
)
from paperless.models import Document, DocumentAttachment, DocumentType, Tag


class StubAgent:
    """Minimal agent stub for engine integration tests."""

    def __init__(self, result: AgentCategorizationResult):
        self._result = result

    def categorize_document(
        self,
        ocr_content: str,
        available_options: AvailableOptions,
        current_metadata: CurrentMetadata,
        attachment: DocumentAttachment | None = None,
    ) -> AgentCategorizationResult:
        del ocr_content, available_options, current_metadata, attachment
        return self._result


class StubPaperless:
    attachment: DocumentAttachment | None = None

    def list_tags(self):
        return [
            Tag(id=1, name="Inbox", slug="inbox", is_inbox_tag=True),
            Tag(id=2, name="financial", slug="financial"),
        ]

    def list_correspondents(self):
        return []

    def list_document_types(self):
        return [DocumentType(id=10, name="Invoice", slug="invoice")]

    def list_storage_paths(self):
        return []

    def download_document_attachment(self, document):
        del document
        return self.attachment


def _make_document() -> Document:
    return Document(
        id=42,
        title="scan.pdf",
        content="Invoice from Acme for $100",
        tags=[1],
        created=datetime(2024, 1, 1),
        created_date="2024-01-01",
        modified=datetime(2024, 1, 1),
        added=datetime(2024, 1, 1),
        original_file_name="scan.pdf",
    )


def test_engine_maps_id_based_output_to_suggestion():
    agent = StubAgent(
        AgentCategorizationResult(
            output=CategorizationAgentOutput(
                title="Invoice - Acme",
                content="Invoice\nAcme Corp\nTotal $100",
                document_type_id=10,
                tag_ids=[2],
                correspondent_id=None,
                new_correspondent_name="Acme Corp",
                storage_path_id=None,
            )
        )
    )
    engine = CategorizationEngine(agent=agent)
    engine.paperless = StubPaperless()
    engine._tags = engine.paperless.list_tags()
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()

    suggestion = engine.categorize_document(_make_document())

    assert suggestion.status == "success"
    assert suggestion.suggested_title == "Invoice - Acme"
    assert suggestion.suggested_content == "Invoice\nAcme Corp\nTotal $100"
    assert suggestion.suggested_type == "Invoice"
    assert suggestion.suggested_type_id == 10
    assert suggestion.suggested_type_is_new is False
    assert suggestion.suggested_tags == ["financial", "Inbox"]
    assert suggestion.suggested_tag_ids == [2, 1]
    assert suggestion.suggested_correspondent == "Acme Corp"
    assert suggestion.suggested_correspondent_is_new is True


def test_engine_preserves_tag_order_when_tag_set_unchanged():
    agent = StubAgent(
        AgentCategorizationResult(
            output=CategorizationAgentOutput(
                title="Invoice - Acme",
                document_type_id=10,
                tag_ids=[3, 2, 1],
                correspondent_id=None,
                new_correspondent_name=None,
                storage_path_id=None,
            )
        )
    )
    engine = CategorizationEngine(agent=agent)
    engine.paperless = StubPaperless()
    engine._tags = [
        Tag(id=1, name="Inbox", slug="inbox", is_inbox_tag=True),
        Tag(id=2, name="financial", slug="financial"),
        Tag(id=3, name="From Email", slug="from-email"),
    ]
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()

    document = Document(
        id=42,
        title="scan.pdf",
        content="Invoice from Acme for $100",
        tags=[1, 2, 3],
        created=datetime(2024, 1, 1),
        created_date="2024-01-01",
        modified=datetime(2024, 1, 1),
        added=datetime(2024, 1, 1),
        original_file_name="scan.pdf",
    )

    suggestion = engine.categorize_document(document)

    assert suggestion.suggested_tag_ids == [1, 2, 3]
    assert suggestion.suggested_tags == ["Inbox", "financial", "From Email"]


def test_engine_preserves_configured_protected_tags():
    agent = StubAgent(
        AgentCategorizationResult(
            output=CategorizationAgentOutput(
                title="Invoice - Acme",
                document_type_id=10,
                tag_ids=[2],
                correspondent_id=None,
                new_correspondent_name=None,
                storage_path_id=None,
            )
        )
    )
    engine = CategorizationEngine(agent=agent, protected_tag_names=["Inbox", "From Email"])
    engine.paperless = StubPaperless()
    engine._tags = [
        Tag(id=1, name="Inbox", slug="inbox", is_inbox_tag=True),
        Tag(id=2, name="financial", slug="financial"),
        Tag(id=3, name="From Email", slug="from-email"),
    ]
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()

    document = _make_document()
    document.tags = [1, 3]

    suggestion = engine.categorize_document(document)

    assert suggestion.suggested_tag_ids == [2, 1, 3]
    assert suggestion.suggested_tags == ["financial", "Inbox", "From Email"]


def test_engine_excludes_configured_protected_tags_from_agent_options():
    captured: dict[str, AvailableOptions] = {}

    class CapturingAgent(StubAgent):
        def categorize_document(
            self,
            ocr_content: str,
            available_options: AvailableOptions,
            current_metadata: CurrentMetadata,
            attachment: DocumentAttachment | None = None,
        ):
            del ocr_content, current_metadata, attachment
            captured["options"] = available_options
            return AgentCategorizationResult(
                output=CategorizationAgentOutput(
                    title="Invoice",
                    document_type_id=10,
                    tag_ids=[2],
                    correspondent_id=None,
                    new_correspondent_name=None,
                    storage_path_id=None,
                )
            )

    engine = CategorizationEngine(
        agent=CapturingAgent(AgentCategorizationResult()),
        protected_tag_names=["Inbox", "From Email"],
    )
    engine.paperless = StubPaperless()
    engine._tags = [
        Tag(id=1, name="Inbox", slug="inbox", is_inbox_tag=True),
        Tag(id=2, name="financial", slug="financial"),
        Tag(id=3, name="From Email", slug="from-email"),
    ]
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()

    engine.categorize_document(_make_document())

    assert captured["options"].tags == [EntityOption(id=2, name="financial")]


def test_engine_excludes_lifecycle_tags_from_agent_options_and_current_metadata():
    captured: dict[str, AvailableOptions | CurrentMetadata] = {}

    class CapturingAgent(StubAgent):
        def categorize_document(
            self,
            ocr_content: str,
            available_options: AvailableOptions,
            current_metadata: CurrentMetadata,
            attachment: DocumentAttachment | None = None,
        ):
            del ocr_content, attachment
            captured["options"] = available_options
            captured["metadata"] = current_metadata
            return AgentCategorizationResult(
                output=CategorizationAgentOutput(
                    title="Invoice",
                    document_type_id=10,
                    tag_ids=[2],
                    correspondent_id=None,
                    new_correspondent_name=None,
                    storage_path_id=None,
                )
            )

    engine = CategorizationEngine(agent=CapturingAgent(AgentCategorizationResult()))
    engine.paperless = StubPaperless()
    engine._tags = [
        Tag(id=1, name="Inbox", slug="inbox", is_inbox_tag=True),
        Tag(id=2, name="financial", slug="financial"),
        Tag(id=3, name="paperless-ai-parsed", slug="paperless-ai-parsed"),
        Tag(id=4, name="paperless-ai-failed", slug="paperless-ai-failed"),
    ]
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()

    document = _make_document()
    document.tags = [1, 2, 3, 4]

    engine.categorize_document(document)

    assert captured["options"].tags == [EntityOption(id=2, name="financial")]
    assert captured["metadata"].tags == [
        EntityOption(id=1, name="Inbox"),
        EntityOption(id=2, name="financial"),
    ]


def test_engine_removes_lifecycle_tags_from_agent_suggestions():
    agent = StubAgent(
        AgentCategorizationResult(
            output=CategorizationAgentOutput(
                title="Invoice - Acme",
                document_type_id=10,
                tag_ids=[2, 3, 4],
                correspondent_id=None,
                new_correspondent_name=None,
                storage_path_id=None,
            )
        )
    )
    engine = CategorizationEngine(agent=agent)
    engine.paperless = StubPaperless()
    engine._tags = [
        Tag(id=1, name="Inbox", slug="inbox", is_inbox_tag=True),
        Tag(id=2, name="financial", slug="financial"),
        Tag(id=3, name="paperless-ai-parsed", slug="paperless-ai-parsed"),
        Tag(id=4, name="paperless-ai-failed", slug="paperless-ai-failed"),
    ]
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()

    suggestion = engine.categorize_document(_make_document())

    assert suggestion.suggested_tag_ids == [2, 1]
    assert suggestion.suggested_tags == ["financial", "Inbox"]


def test_engine_maps_pending_correspondent_id_to_new_suggestion():
    agent = StubAgent(
        AgentCategorizationResult(
            output=CategorizationAgentOutput(
                title="Invoice - Acme",
                document_type_id=10,
                tag_ids=[2],
                correspondent_id=-1,
                new_correspondent_name=None,
                storage_path_id=None,
            )
        )
    )
    engine = CategorizationEngine(agent=agent)
    engine.paperless = StubPaperless()
    engine._tags = engine.paperless.list_tags()
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()
    engine.new_entities_found["correspondents"]["Acme Corp"] = [99]

    suggestion = engine.categorize_document(_make_document())

    assert suggestion.suggested_correspondent == "Acme Corp"
    assert suggestion.suggested_correspondent_id == -1
    assert suggestion.suggested_correspondent_is_new is True


def test_engine_forwards_current_metadata_to_agent():
    captured: dict[str, CurrentMetadata] = {}

    class CapturingAgent(StubAgent):
        def categorize_document(
            self,
            ocr_content: str,
            available_options: AvailableOptions,
            current_metadata: CurrentMetadata,
            attachment: DocumentAttachment | None = None,
        ):
            del ocr_content, available_options, attachment
            captured["metadata"] = current_metadata
            return AgentCategorizationResult(
                output=CategorizationAgentOutput(
                    title="Invoice",
                    document_type_id=10,
                    tag_ids=[2],
                    correspondent_id=None,
                    new_correspondent_name=None,
                    storage_path_id=None,
                )
            )

    engine = CategorizationEngine(agent=CapturingAgent(AgentCategorizationResult()))
    engine.paperless = StubPaperless()
    engine._tags = engine.paperless.list_tags()
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()

    engine.categorize_document(_make_document())

    metadata = captured["metadata"]
    assert metadata.title == "scan.pdf"
    assert metadata.document_type is None
    assert metadata.tags == [EntityOption(id=1, name="Inbox")]
    assert metadata.correspondent is None
    assert metadata.storage_path is None


def test_engine_includes_pending_correspondents_in_agent_options():
    captured: dict[str, AvailableOptions] = {}

    class CapturingAgent(StubAgent):
        def categorize_document(
            self,
            ocr_content: str,
            available_options: AvailableOptions,
            current_metadata: CurrentMetadata,
            attachment: DocumentAttachment | None = None,
        ):
            del ocr_content, current_metadata, attachment
            captured["options"] = available_options
            return AgentCategorizationResult(
                output=CategorizationAgentOutput(
                    title="Invoice",
                    document_type_id=10,
                    tag_ids=[2],
                    correspondent_id=None,
                    new_correspondent_name=None,
                    storage_path_id=None,
                )
            )

    engine = CategorizationEngine(agent=CapturingAgent(AgentCategorizationResult()))
    engine.paperless = StubPaperless()
    engine._tags = engine.paperless.list_tags()
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()
    engine.new_entities_found["correspondents"]["Acme Corp"] = [99]

    engine.categorize_document(_make_document())

    assert captured["options"].correspondents == [EntityOption(id=-1, name="Acme Corp")]


def test_engine_excludes_tracking_tags_from_agent_options():
    captured: dict[str, AvailableOptions] = {}

    class CapturingAgent(StubAgent):
        def categorize_document(
            self,
            ocr_content: str,
            available_options: AvailableOptions,
            current_metadata: CurrentMetadata,
            attachment: DocumentAttachment | None = None,
        ):
            del ocr_content, current_metadata, attachment
            captured["options"] = available_options
            return AgentCategorizationResult(
                output=CategorizationAgentOutput(
                    title="Invoice",
                    document_type_id=10,
                    tag_ids=[2],
                    correspondent_id=None,
                    new_correspondent_name=None,
                    storage_path_id=None,
                )
            )

    engine = CategorizationEngine(agent=CapturingAgent(AgentCategorizationResult()))
    engine.paperless = StubPaperless()
    engine._tags = [
        Tag(id=1, name="Inbox", slug="inbox", is_inbox_tag=True),
        Tag(id=2, name="financial", slug="financial"),
        Tag(id=3, name=PARSED_TAG_NAME, slug="paperless-ai-parsed"),
        Tag(id=4, name=FAILED_TAG_NAME, slug="paperless-ai-failed"),
    ]
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()

    engine.categorize_document(_make_document())

    assert captured["options"].tags == [EntityOption(id=2, name="financial")]


def test_engine_resolves_pending_correspondent_id_for_apply():
    from paperless.models import Correspondent

    engine = CategorizationEngine(agent=StubAgent(AgentCategorizationResult()))
    engine.paperless = StubPaperless()
    engine._correspondents = [Correspondent(id=55, name="Acme Corp", slug="acme")]
    engine.new_entities_found["correspondents"]["Acme Corp"] = [42]

    class Suggestion:
        suggested_correspondent_id = -1
        suggested_correspondent = "Acme Corp"
        suggested_correspondent_is_new = True

    assert engine.resolve_suggestion_correspondent_id(Suggestion()) == 55


def test_engine_resolves_pending_correspondent_by_stored_name_after_pending_list_changes():
    from paperless.models import Correspondent

    engine = CategorizationEngine(agent=StubAgent(AgentCategorizationResult()))
    engine.paperless = StubPaperless()
    engine._correspondents = [
        Correspondent(id=55, name="Acme Corp", slug="acme"),
        Correspondent(id=66, name="Beta Corp", slug="beta"),
    ]
    engine.new_entities_found["correspondents"]["Beta Corp"] = [43]

    class Suggestion:
        suggested_correspondent_id = -1
        suggested_correspondent = "Acme Corp"
        suggested_correspondent_is_new = True

    assert engine.resolve_suggestion_correspondent_id(Suggestion()) == 55


def test_engine_has_unresolved_new_correspondent_when_not_in_paperless():
    engine = CategorizationEngine(agent=StubAgent(AgentCategorizationResult()))
    engine.paperless = StubPaperless()
    engine._correspondents = []

    class Suggestion:
        status = "success"
        suggested_correspondent_is_new = True
        suggested_correspondent = "Acme Corp"
        suggested_correspondent_id = None

    assert engine.has_unresolved_new_correspondent(Suggestion()) is True


def test_remove_pending_correspondents_drops_pseudo_options():
    engine = CategorizationEngine(agent=StubAgent(AgentCategorizationResult()))
    engine.paperless = StubPaperless()
    engine.new_entities_found["correspondents"]["Acme Corp"] = [42]

    engine.remove_pending_correspondents(["Acme Corp"])

    assert "Acme Corp" not in engine.new_entities_found["correspondents"]


def test_engine_calls_agent_for_empty_ocr_when_attachment_exists(tmp_path):
    captured: dict[str, str | DocumentAttachment | None] = {}
    attachment_path = tmp_path / "source.pdf"
    attachment_path.write_bytes(b"%PDF")

    class CapturingAgent(StubAgent):
        def categorize_document(
            self,
            ocr_content: str,
            available_options: AvailableOptions,
            current_metadata: CurrentMetadata,
            attachment: DocumentAttachment | None = None,
        ):
            del available_options, current_metadata
            captured["ocr_content"] = ocr_content
            captured["attachment"] = attachment
            return AgentCategorizationResult(
                output=CategorizationAgentOutput(
                    title="Attachment only",
                    content="Extracted text from attachment",
                    document_type_id=10,
                    tag_ids=[2],
                    correspondent_id=None,
                    new_correspondent_name=None,
                    storage_path_id=None,
                )
            )

    paperless = StubPaperless()
    paperless.attachment = DocumentAttachment(
        path=str(attachment_path),
        source="archived",
        mime_type="application/pdf",
        filename="source.pdf",
    )
    engine = CategorizationEngine(agent=CapturingAgent(AgentCategorizationResult()))
    engine.paperless = paperless
    engine._tags = engine.paperless.list_tags()
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()
    document = _make_document()
    document.content = ""

    suggestion = engine.categorize_document(document)

    assert suggestion.status == "success"
    assert suggestion.suggested_content == "Extracted text from attachment"
    assert captured["ocr_content"] == ""
    assert captured["attachment"] == paperless.attachment
    assert not attachment_path.exists()


def test_engine_returns_error_for_empty_ocr_when_attachment_yields_no_content(tmp_path):
    attachment_path = tmp_path / "source.pdf"
    attachment_path.write_bytes(b"%PDF")

    paperless = StubPaperless()
    paperless.attachment = DocumentAttachment(
        path=str(attachment_path),
        source="archived",
        mime_type="application/pdf",
        filename="source.pdf",
    )
    engine = CategorizationEngine(
        agent=StubAgent(
            AgentCategorizationResult(
                output=CategorizationAgentOutput(
                    title="Attachment only",
                    content=None,
                    document_type_id=10,
                    tag_ids=[2],
                    correspondent_id=None,
                    new_correspondent_name=None,
                    storage_path_id=None,
                )
            )
        )
    )
    engine.paperless = paperless
    engine._tags = engine.paperless.list_tags()
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()
    document = _make_document()
    document.content = ""

    suggestion = engine.categorize_document(document)

    assert suggestion.status == "error"
    assert suggestion.error_message == "Document attachment did not provide usable OCR content"
    assert not attachment_path.exists()


def test_engine_returns_error_for_empty_ocr_without_attachment():
    engine = CategorizationEngine(agent=StubAgent(AgentCategorizationResult()))
    engine.paperless = StubPaperless()
    engine._tags = engine.paperless.list_tags()
    engine._correspondents = engine.paperless.list_correspondents()
    engine._document_types = engine.paperless.list_document_types()
    engine._storage_paths = engine.paperless.list_storage_paths()
    document = _make_document()
    document.content = ""

    suggestion = engine.categorize_document(document)

    assert suggestion.status == "error"
    assert suggestion.error_message == "Document has no OCR content or supported attachment"
