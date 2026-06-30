"""Tests for categorization prompt assembly."""

from llm.prompts import (
    build_categorization_prompt,
    build_categorization_prompt_with_files,
    materialize_prompt_for_debug,
)
from llm.schemas import AvailableOptions, EntityOption


def test_build_categorization_prompt_puts_instructions_before_data():
    prompt = build_categorization_prompt(
        content="Invoice total $42",
        available_options=AvailableOptions(
            document_types=[EntityOption(id=1, name="Bill")],
        ),
    )

    instructions_index = prompt.index("CORRESPONDENT MATCHING:")
    ocr_index = prompt.index("<ocr_content>")
    options_index = prompt.index("<available_options>")

    assert instructions_index < ocr_index < options_index
    assert "Invoice total $42" in prompt
    assert '"document_types":[{"id":1,"name":"Bill"}]' in prompt


def test_build_categorization_prompt_with_files_puts_instructions_before_refs():
    prompt = build_categorization_prompt_with_files(
        ocr_path="/tmp/ocr.txt",
        options_path="/tmp/options.json",
    )

    instructions_index = prompt.index("SEMANTIC TAG MATCHING:")
    ocr_ref_index = prompt.index("@/tmp/ocr.txt")
    options_ref_index = prompt.index("@/tmp/options.json")

    assert instructions_index < ocr_ref_index < options_ref_index


def test_materialize_prompt_for_debug_inlines_file_backed_prompt():
    file_prompt = build_categorization_prompt_with_files(
        ocr_path="/tmp/ocr.txt",
        options_path="/tmp/options.json",
    )
    options = AvailableOptions(
        document_types=[EntityOption(id=1, name="Bill")],
    )

    resolved = materialize_prompt_for_debug(
        file_prompt,
        content="Invoice total $42",
        available_options=options,
    )

    assert resolved is not None
    assert "@/tmp/ocr.txt" not in resolved
    assert "Invoice total $42" in resolved
    assert '"document_types":[{"id":1,"name":"Bill"}]' in resolved
