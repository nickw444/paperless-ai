"""Tests for mapping agent JSON output through the categorization engine."""

from datetime import datetime

from categorizer.engine import CategorizationEngine
from llm.base import CommandLineAgent
from llm.schemas import (
    AgentCategorizationResult,
    AvailableOptions,
    CategorizationAgentOutput,
    EntityOption,
)
from paperless.models import Document, DocumentType, Tag


class StubAgent(CommandLineAgent):
    """Minimal agent stub for engine integration tests."""

    def __init__(self, result: AgentCategorizationResult):
        super().__init__(timeout=1, max_content_chars=1000, max_retries=1)
        self._result = result

    def categorize_document(
        self,
        ocr_content: str,
        available_options: AvailableOptions,
    ) -> AgentCategorizationResult:
        del ocr_content, available_options
        return self._result

    def _extract_structured_payload(self, stdout: str, output_path: str | None) -> dict:
        raise NotImplementedError

    def _build_prompt(self, **kwargs) -> str:
        raise NotImplementedError

    def _build_subprocess_args(self, **kwargs):
        raise NotImplementedError


class StubPaperless:
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
    assert suggestion.suggested_type == "Invoice"
    assert suggestion.suggested_type_id == 10
    assert suggestion.suggested_type_is_new is False
    assert suggestion.suggested_tags == ["financial", "Inbox"]
    assert suggestion.suggested_tag_ids == [2, 1]
    assert suggestion.suggested_correspondent == "Acme Corp"
    assert suggestion.suggested_correspondent_is_new is True


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


def test_engine_includes_pending_correspondents_in_agent_options():
    captured: dict[str, AvailableOptions] = {}

    class CapturingAgent(StubAgent):
        def categorize_document(self, ocr_content: str, available_options: AvailableOptions):
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
