"""Tests for categorization prompt assembly."""

from llm.prompts import (
    build_categorization_instructions,
    build_categorization_prompt,
    format_current_metadata_json,
)
from llm.schemas import AvailableOptions, CurrentMetadata, EntityOption, GuidedEntityOption
from paperless.models import DocumentAttachment


def _sample_current_metadata() -> CurrentMetadata:
    return CurrentMetadata(
        title="scan.pdf",
        document_date="2024-01-01",
        document_type=None,
        tags=[EntityOption(id=1, name="Inbox")],
        correspondent=None,
        storage_path=None,
    )


def test_build_categorization_prompt_puts_instructions_before_data():
    prompt = build_categorization_prompt(
        content="Invoice total $42",
        available_options=AvailableOptions(
            document_types=[GuidedEntityOption(id=1, name="Bill", use_when="Payment requested")],
        ),
        current_metadata=_sample_current_metadata(),
    )

    instructions_index = prompt.index("CORRESPONDENT MATCHING:")
    metadata_index = prompt.index("<current_metadata>")
    ocr_index = prompt.index("<ocr_content>")
    options_index = prompt.index("<available_options>")

    assert instructions_index < metadata_index < ocr_index < options_index
    assert "Invoice total $42" in prompt
    assert '"document_types":[{"id":1,"name":"Bill","use_when":"Payment requested"}]' in prompt
    assert '"title":"scan.pdf"' in prompt
    assert '"document_date":"2024-01-01"' in prompt
    assert '"tags":[{"id":1,"name":"Inbox"}]' in prompt
    assert "Set document_date to the document's own date" in prompt
    assert "letterhead" in prompt
    assert "Set content to corrected document OCR text" in prompt
    assert "Do not summarize" in prompt
    assert "photo or image without clear document text" in prompt
    assert "factual description of what is visible" in prompt


def test_build_categorization_prompt_includes_attachment_block():
    prompt = build_categorization_prompt(
        content="Invoice total $42",
        available_options=AvailableOptions(),
        current_metadata=_sample_current_metadata(),
        attachment=DocumentAttachment(
            path="/tmp/source.pdf",
            source="archived",
            mime_type="application/pdf",
            filename="source.pdf",
            byte_size=123,
        ),
    )

    attachment_index = prompt.index("<document_attachment>")
    metadata_index = prompt.index("<current_metadata>")

    assert attachment_index < metadata_index
    assert "@/tmp/source.pdf" in prompt
    assert "mime_type: application/pdf" in prompt
    assert "filename: source.pdf" in prompt


def test_build_categorization_prompt_tells_agent_to_describe_textless_photos():
    prompt = build_categorization_prompt(
        content="",
        available_options=AvailableOptions(),
        current_metadata=_sample_current_metadata(),
        attachment=DocumentAttachment(
            path="/tmp/photo.jpg",
            source="original",
            mime_type="image/jpeg",
            filename="IMG_1234.jpg",
            byte_size=456,
        ),
    )

    assert "extract usable text from the attachment" in prompt
    assert "set content to a concise" in prompt
    assert "augment generic titles" in prompt
    assert "mime_type: image/jpeg" in prompt


def test_categorization_instructions_require_guided_metadata_options():
    instructions = build_categorization_instructions()

    assert "SEMANTIC TAG MATCHING:" in instructions
    assert "primarily ABOUT" in instructions
    assert "available_options.document_types" in instructions
    assert "available_options.tags" in instructions
    assert "Do not force a storage path" in instructions


def test_format_current_metadata_json_is_compact():
    rendered = format_current_metadata_json(
        CurrentMetadata(
            title="Manual Title",
            document_date="2024-01-15",
            tags=[
                EntityOption(id=2, name="financial"),
                EntityOption(id=1, name="Inbox"),
            ],
            correspondent=EntityOption(id=5, name="Acme Corp"),
        )
    )

    assert "\n" not in rendered
    assert '"title":"Manual Title"' in rendered
    assert '"document_date":"2024-01-15"' in rendered
    assert '"tags":[{"id":2,"name":"financial"},{"id":1,"name":"Inbox"}]' in rendered
    assert '"correspondent":{"id":5,"name":"Acme Corp"}' in rendered
