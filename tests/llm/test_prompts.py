"""Tests for categorization prompt assembly."""

from llm.prompts import (
    build_categorization_prompt,
    build_categorization_prompt_with_files,
    format_current_metadata_json,
    materialize_prompt_for_debug,
)
from llm.schemas import AvailableOptions, CurrentMetadata, EntityOption


def _sample_current_metadata() -> CurrentMetadata:
    return CurrentMetadata(
        title="scan.pdf",
        document_type=None,
        tags=[EntityOption(id=1, name="Inbox")],
        correspondent=None,
        storage_path=None,
    )


def test_build_categorization_prompt_puts_instructions_before_data():
    prompt = build_categorization_prompt(
        content="Invoice total $42",
        available_options=AvailableOptions(
            document_types=[EntityOption(id=1, name="Bill")],
        ),
        current_metadata=_sample_current_metadata(),
    )

    instructions_index = prompt.index("CORRESPONDENT MATCHING:")
    metadata_index = prompt.index("<current_metadata>")
    ocr_index = prompt.index("<ocr_content>")
    options_index = prompt.index("<available_options>")

    assert instructions_index < metadata_index < ocr_index < options_index
    assert "Invoice total $42" in prompt
    assert '"document_types":[{"id":1,"name":"Bill"}]' in prompt
    assert '"title":"scan.pdf"' in prompt
    assert '"tags":[{"id":1,"name":"Inbox"}]' in prompt


def test_build_categorization_prompt_with_files_puts_instructions_before_refs():
    prompt = build_categorization_prompt_with_files(
        ocr_path="/tmp/ocr.txt",
        options_path="/tmp/options.json",
        current_metadata=_sample_current_metadata(),
    )

    instructions_index = prompt.index("SEMANTIC TAG MATCHING:")
    metadata_index = prompt.index("<current_metadata>")
    ocr_ref_index = prompt.index("@/tmp/ocr.txt")
    options_ref_index = prompt.index("@/tmp/options.json")

    assert instructions_index < metadata_index < ocr_ref_index < options_ref_index
    assert '"title":"scan.pdf"' in prompt


def test_materialize_prompt_for_debug_inlines_file_backed_prompt():
    file_prompt = build_categorization_prompt_with_files(
        ocr_path="/tmp/ocr.txt",
        options_path="/tmp/options.json",
        current_metadata=_sample_current_metadata(),
    )
    options = AvailableOptions(
        document_types=[EntityOption(id=1, name="Bill")],
    )

    resolved = materialize_prompt_for_debug(
        file_prompt,
        content="Invoice total $42",
        available_options=options,
        current_metadata=_sample_current_metadata(),
    )

    assert resolved is not None
    assert "@/tmp/ocr.txt" not in resolved
    assert "Invoice total $42" in resolved
    assert '"document_types":[{"id":1,"name":"Bill"}]' in resolved
    assert '"title":"scan.pdf"' in resolved


def test_format_current_metadata_json_is_compact():
    rendered = format_current_metadata_json(
        CurrentMetadata(
            title="Manual Title",
            tags=[
                EntityOption(id=2, name="financial"),
                EntityOption(id=1, name="Inbox"),
            ],
            correspondent=EntityOption(id=5, name="Acme Corp"),
        )
    )

    assert "\n" not in rendered
    assert '"title":"Manual Title"' in rendered
    assert '"tags":[{"id":2,"name":"financial"},{"id":1,"name":"Inbox"}]' in rendered
    assert '"correspondent":{"id":5,"name":"Acme Corp"}' in rendered
