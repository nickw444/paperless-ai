"""Tests for JSON schema building and validation."""

import json

import pytest
from pydantic import ValidationError

from llm.prompts import format_available_options_json
from llm.schemas import (
    AvailableOptions,
    CategorizationAgentOutput,
    CurrentMetadata,
    EntityOption,
    GuidedEntityOption,
    build_categorization_json_schema,
    is_pending_correspondent_id,
    merge_correspondent_options,
    pending_correspondent_id,
    pending_correspondent_name,
    schema_uses_forbidden_keywords,
    validate_agent_output,
)


def _sample_options() -> AvailableOptions:
    return AvailableOptions(
        document_types=[
            GuidedEntityOption(id=10, name="Invoice", use_when="Invoices"),
            GuidedEntityOption(id=11, name="Receipt", use_when="Receipts"),
        ],
        tags=[
            GuidedEntityOption(id=2, name="financial", use_when="Financial"),
            GuidedEntityOption(id=3, name="2024", use_when="Year 2024"),
        ],
        correspondents=[EntityOption(id=5, name="Acme Corp")],
        storage_paths=[GuidedEntityOption(id=7, name="Bills", use_when="Household bills")],
    )


def test_build_categorization_json_schema_is_static_and_compact():
    schema = build_categorization_json_schema()

    assert schema["additionalProperties"] is False
    assert schema_uses_forbidden_keywords(schema) is False
    assert "enum" not in json.dumps(schema)

    assert schema["properties"]["content"] == {"type": ["string", "null"]}
    assert schema["properties"]["document_date"] == {"type": ["string", "null"]}
    assert schema["properties"]["document_type_id"] == {"type": ["integer", "null"]}
    assert schema["properties"]["tag_ids"] == {
        "type": "array",
        "items": {"type": "integer"},
    }
    assert schema["properties"]["correspondent_id"] == {"type": ["integer", "null"]}
    assert schema["properties"]["storage_path_id"] == {"type": ["integer", "null"]}
    assert schema["properties"]["new_correspondent_name"]["type"] == ["string", "null"]


def test_build_categorization_json_schema_does_not_vary_with_options():
    schema_a = build_categorization_json_schema()
    schema_b = build_categorization_json_schema()
    assert schema_a == schema_b


def test_build_categorization_json_schema_is_json_serializable():
    schema = build_categorization_json_schema()
    serialized = json.dumps(schema)
    assert "oneOf" not in serialized


def test_format_available_options_json_is_compact():
    options = _sample_options()
    rendered = format_available_options_json(options)

    assert "\n" not in rendered
    parsed = json.loads(rendered)
    assert parsed["document_types"][0] == {
        "id": 10,
        "name": "Invoice",
        "use_when": "Invoices",
    }
    assert parsed["storage_paths"][0] == {
        "id": 7,
        "name": "Bills",
        "use_when": "Household bills",
    }
    assert "pending_correspondents" not in parsed


def test_validate_categorization_output_accepts_valid_payload():
    options = _sample_options()
    output = validate_agent_output(
        CategorizationAgentOutput.model_validate(
            {
                "title": "Invoice - Acme - Jan 2024",
                "content": "Invoice\nAcme\nTotal $42",
                "document_date": "2024-01-15",
                "document_type_id": 10,
                "tag_ids": [2],
                "correspondent_id": 5,
                "new_correspondent_name": None,
                "storage_path_id": None,
            }
        ),
        options,
    )

    assert output.title == "Invoice - Acme - Jan 2024"
    assert output.content == "Invoice\nAcme\nTotal $42"
    assert output.document_date.isoformat() == "2024-01-15"
    assert output.document_type_id == 10
    assert output.tag_ids == [2]


def test_validate_agent_output_rejects_invalid_tag_id():
    options = _sample_options()
    output = CategorizationAgentOutput.model_validate(
        {
            "title": "Test",
            "document_type_id": None,
            "tag_ids": [999],
            "correspondent_id": None,
            "new_correspondent_name": None,
            "storage_path_id": None,
        }
    )

    with pytest.raises(ValueError, match="Invalid tag_ids"):
        validate_agent_output(output, options)


def test_validate_agent_output_rejects_duplicate_tags():
    options = _sample_options()
    output = CategorizationAgentOutput.model_validate(
        {
            "title": "Test",
            "document_type_id": None,
            "tag_ids": [2, 2],
            "correspondent_id": None,
            "new_correspondent_name": None,
            "storage_path_id": None,
        }
    )

    with pytest.raises(ValueError, match="unique"):
        validate_agent_output(output, options)


def test_validate_agent_output_rejects_new_name_matching_existing():
    options = _sample_options()
    output = CategorizationAgentOutput.model_validate(
        {
            "title": "Test",
            "document_type_id": None,
            "tag_ids": [],
            "correspondent_id": None,
            "new_correspondent_name": "acme corp",
            "storage_path_id": None,
        }
    )

    with pytest.raises(ValueError, match="matches existing correspondent"):
        validate_agent_output(output, options)


def test_categorization_output_rejects_both_correspondent_fields():
    with pytest.raises(ValidationError):
        CategorizationAgentOutput.model_validate(
            {
                "title": "Test",
                "document_type_id": None,
                "tag_ids": [],
                "correspondent_id": 5,
                "new_correspondent_name": "New Corp",
                "storage_path_id": None,
            }
        )


def test_merge_correspondent_options_appends_pending_with_negative_ids():
    merged = merge_correspondent_options(
        [EntityOption(id=5, name="Acme Corp")],
        ["Pending Co", "Another Pending"],
    )

    assert merged == [
        EntityOption(id=5, name="Acme Corp"),
        EntityOption(id=-1, name="Pending Co"),
        EntityOption(id=-2, name="Another Pending"),
    ]


def test_pending_correspondent_name_round_trip():
    pending_names = ["Pending Co", "Another Pending"]
    assert pending_correspondent_name(pending_correspondent_id(0), pending_names) == "Pending Co"
    assert pending_correspondent_name(pending_correspondent_id(1), pending_names) == (
        "Another Pending"
    )
    assert is_pending_correspondent_id(-1) is True
    assert is_pending_correspondent_id(5) is False


def test_validate_agent_output_accepts_pending_correspondent_id():
    options = AvailableOptions(
        correspondents=merge_correspondent_options(
            [EntityOption(id=5, name="Acme Corp")],
            ["Pending Co"],
        ),
    )
    output = validate_agent_output(
        CategorizationAgentOutput.model_validate(
            {
                "title": "Invoice",
                "document_type_id": None,
                "tag_ids": [],
                "correspondent_id": -1,
                "new_correspondent_name": None,
                "storage_path_id": None,
            }
        ),
        options,
    )

    assert output.correspondent_id == -1


def test_validate_categorization_output_rejects_missing_title():
    with pytest.raises(ValidationError):
        CategorizationAgentOutput.model_validate({"tag_ids": []})


def test_categorization_output_normalizes_blank_content_to_null():
    output = CategorizationAgentOutput.model_validate(
        {
            "title": "Test",
            "content": "   \n\t",
            "document_type_id": None,
            "tag_ids": [],
            "correspondent_id": None,
            "new_correspondent_name": None,
            "storage_path_id": None,
        }
    )

    assert output.content is None


def test_current_metadata_defaults_optional_fields():
    metadata = CurrentMetadata(title="scan.pdf")

    assert metadata.title == "scan.pdf"
    assert metadata.document_date is None
    assert metadata.document_type is None
    assert metadata.tags == []
    assert metadata.correspondent is None
    assert metadata.storage_path is None


def test_current_metadata_serializes_entity_options():
    metadata = CurrentMetadata(
        title="Invoice",
        document_date="2024-01-15",
        document_type=EntityOption(id=10, name="Invoice"),
        tags=[EntityOption(id=1, name="Inbox")],
        correspondent=EntityOption(id=5, name="Acme Corp"),
        storage_path=EntityOption(id=7, name="Bills"),
    )

    assert metadata.document_type == EntityOption(id=10, name="Invoice")
    assert metadata.document_date.isoformat() == "2024-01-15"
    assert metadata.correspondent == EntityOption(id=5, name="Acme Corp")
