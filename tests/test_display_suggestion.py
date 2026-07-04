"""Tests for console suggestion rendering."""

from io import StringIO

from rich.console import Console

from main import _display_suggestion
from paperless.models import CategorizationSuggestion


def _render_suggestion(suggestion: CategorizationSuggestion) -> str:
    output = StringIO()
    console = Console(file=output, width=120, color_system=None)

    _display_suggestion(suggestion, output_console=console)

    return output.getvalue()


def test_display_suggestion_shows_empty_storage_path():
    rendered = _render_suggestion(
        CategorizationSuggestion(
            document_id=42,
            current_title="scan.pdf",
            suggested_title="Invoice",
        )
    )

    assert "Storage Path: None" in rendered


def test_display_suggestion_shows_storage_path_change():
    rendered = _render_suggestion(
        CategorizationSuggestion(
            document_id=42,
            current_title="scan.pdf",
            suggested_title="Invoice",
            current_storage_path_name="None",
            suggested_storage_path="Household",
            suggested_storage_path_id=31,
        )
    )

    assert "Storage Path: None -> Household" in rendered
