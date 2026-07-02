"""Tests for apply confirmation behavior."""

from datetime import UTC, datetime

from click.testing import CliRunner

from main import _confirm_or_yes, _review_new_entities_and_apply, cli
from paperless.models import CategorizationSuggestion, Document


def test_analyze_exposes_yes_flag():
    result = CliRunner().invoke(cli, ["analyze", "--help"])

    assert result.exit_code == 0
    assert "-y, --yes" in result.output
    assert "Automatically confirm apply-time prompts" in result.output
    assert "--apply" not in result.output


def test_confirm_or_yes_skips_prompt_when_yes_is_set():
    prompts: list[str] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return False

    assert _confirm_or_yes("Apply changes?", yes=True, confirm=confirm) is True
    assert prompts == []


def test_confirm_or_yes_uses_prompt_without_yes():
    prompts: list[str] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return True

    assert _confirm_or_yes("Apply changes?", yes=False, confirm=confirm) is True
    assert prompts == ["Apply changes?"]


class ReviewEngine:
    """Engine stub for review/apply flow tests."""

    def __init__(self):
        self.new_entities_found = {"correspondents": {}}
        self.documents_with_new_entities: set[int] = set()
        self.last_agent_result = None
        self.categorized_documents: list[int] = []

    def categorize_document(self, document):
        self.categorized_documents.append(document.id)
        return _suggestion(document.id, suggested_correspondent="Acme Corp")


def test_review_flow_prompts_to_apply_suggestions_by_default():
    engine = ReviewEngine()
    suggestions = [_suggestion(42)]
    prompts: list[str] = []
    applied: list[list[CategorizationSuggestion]] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return True

    _review_new_entities_and_apply(
        engine,
        [_document(42)],
        suggestions,
        yes=False,
        confirm=confirm,
        apply_suggestions=lambda _, suggestions: applied.append(list(suggestions)),
    )

    assert prompts == ["\nApply categorization suggestions to documents?"]
    assert applied == [suggestions]


def test_review_flow_yes_creates_recategorizes_and_applies_without_prompts():
    engine = ReviewEngine()
    engine.new_entities_found = {"correspondents": {"Acme Corp": [42]}}
    engine.documents_with_new_entities = {42}
    suggestions = [_suggestion(42, suggested_correspondent="Acme Corp", is_new=True)]
    prompts: list[str] = []
    applied: list[list[CategorizationSuggestion]] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return False

    _review_new_entities_and_apply(
        engine,
        [_document(42)],
        suggestions,
        yes=True,
        confirm=confirm,
        create_new_entities=lambda _, __: {"correspondents": 1},
        apply_suggestions=lambda _, suggestions: applied.append(list(suggestions)),
    )

    assert prompts == []
    assert engine.categorized_documents == [42]
    assert engine.documents_with_new_entities == set()
    assert applied == [suggestions]
    assert suggestions[0].suggested_correspondent_is_new is False


def _document(document_id: int) -> Document:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    return Document(
        id=document_id,
        title="scan.pdf",
        created=timestamp,
        created_date="2026-01-01",
        modified=timestamp,
        added=timestamp,
        original_file_name="scan.pdf",
    )


def _suggestion(
    document_id: int,
    *,
    suggested_correspondent: str | None = None,
    is_new: bool = False,
) -> CategorizationSuggestion:
    return CategorizationSuggestion(
        document_id=document_id,
        current_title="scan.pdf",
        suggested_title="Updated title",
        suggested_correspondent=suggested_correspondent,
        suggested_correspondent_is_new=is_new,
    )
