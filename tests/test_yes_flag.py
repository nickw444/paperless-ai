"""Tests for apply confirmation behavior."""

from click.testing import CliRunner

from main import _confirm_or_yes, _review_new_entities_and_apply, cli
from paperless.models import CategorizationSuggestion


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
        suggestions,
        yes=False,
        confirm=confirm,
        apply_suggestions=lambda _, suggestions: applied.append(list(suggestions)),
    )

    assert prompts == ["\nApply categorization suggestions to documents?"]
    assert applied == [suggestions]


def test_review_flow_yes_creates_correspondents_and_applies_without_prompts():
    engine = ReviewEngine()
    engine.new_entities_found = {"correspondents": {"Acme Corp": [42]}}
    suggestions = [_suggestion(42, suggested_correspondent="Acme Corp", is_new=True)]
    prompts: list[str] = []
    created: list[dict] = []
    applied: list[list[CategorizationSuggestion]] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return False

    _review_new_entities_and_apply(
        engine,
        suggestions,
        yes=True,
        confirm=confirm,
        create_new_entities=lambda _, new_entities: (
            created.append(new_entities) or {"correspondents": 1}
        ),
        apply_suggestions=lambda _, suggestions: applied.append(list(suggestions)),
    )

    assert prompts == []
    assert created == [{"correspondents": {"Acme Corp": [42]}}]
    assert applied == [suggestions]


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
