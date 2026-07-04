"""Pydantic models and JSON Schema builders for agent categorization output."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

from llm.usage import AgentUsageMetadata
from paperless.models import DocumentAttachment


class EntityOption(BaseModel):
    """A selectable Paperless entity with id and display name."""

    id: int
    name: str


class GuidedEntityOption(BaseModel):
    """A selectable tag or document type with embedded usage guidance."""

    id: int
    name: str
    use_when: str | None = None
    avoid_when: str | None = None
    protected: bool | None = None


class CategorizationAgentOutput(BaseModel):
    """Validated categorization fields returned by the agent (ID-based)."""

    title: str
    content: str | None = None
    document_date: date | None = None
    document_type_id: int | None = None
    tag_ids: list[int] = Field(default_factory=list)
    correspondent_id: int | None = None
    new_correspondent_name: str | None = None
    storage_path_id: int | None = None

    @model_validator(mode="after")
    def validate_correspondent_fields(self) -> CategorizationAgentOutput:
        """Ensure correspondent_id and new_correspondent_name are not both set."""
        if self.correspondent_id is not None and self.new_correspondent_name is not None:
            raise ValueError("correspondent_id and new_correspondent_name cannot both be set")
        if self.new_correspondent_name is not None:
            stripped = self.new_correspondent_name.strip()
            if not stripped:
                raise ValueError("new_correspondent_name cannot be empty")
            self.new_correspondent_name = stripped
        if self.content is not None and not self.content.strip():
            self.content = None
        return self


class CurrentMetadata(BaseModel):
    """Existing Paperless metadata for a document before categorization."""

    title: str
    document_date: date | None = None
    document_type: EntityOption | None = None
    tags: list[EntityOption] = Field(default_factory=list)
    correspondent: EntityOption | None = None
    storage_path: EntityOption | None = None


class AvailableOptions(BaseModel):
    """Structured Paperless metadata options passed to the agent."""

    document_types: list[GuidedEntityOption] = Field(default_factory=list)
    tags: list[GuidedEntityOption] = Field(default_factory=list)
    correspondents: list[EntityOption] = Field(default_factory=list)
    storage_paths: list[GuidedEntityOption] = Field(default_factory=list)

    def document_type_ids(self) -> list[int]:
        return [option.id for option in self.document_types]

    def tag_ids(self) -> list[int]:
        return [option.id for option in self.tags]

    def correspondent_ids(self) -> list[int]:
        return [option.id for option in self.correspondents]

    def storage_path_ids(self) -> list[int]:
        return [option.id for option in self.storage_paths]

    def correspondent_names_lower(self) -> set[str]:
        return {option.name.lower() for option in self.correspondents}


class AttachmentDebugMetadata(BaseModel):
    """Safe-to-print metadata for a document attachment."""

    path: str
    source: str
    mime_type: str
    filename: str
    byte_size: int | None = None


def is_pending_correspondent_id(correspondent_id: int) -> bool:
    """Return True when the id is a batch-local pseudo id for a pending correspondent."""
    return correspondent_id < 0


def pending_correspondent_id(index: int) -> int:
    """Map a pending correspondent list index to its pseudo id (-1, -2, ...)."""
    return -(index + 1)


def pending_correspondent_index(correspondent_id: int) -> int:
    """Map a pending pseudo id back to its index in the pending list."""
    return -(correspondent_id + 1)


def pending_correspondent_name(
    correspondent_id: int,
    pending_names: list[str],
) -> str | None:
    """Resolve a pending pseudo id to the correspondent name for this batch."""
    if not is_pending_correspondent_id(correspondent_id):
        return None
    index = pending_correspondent_index(correspondent_id)
    if 0 <= index < len(pending_names):
        return pending_names[index]
    return None


def merge_correspondent_options(
    correspondents: list[EntityOption],
    pending_names: list[str],
) -> list[EntityOption]:
    """Append batch-local pending correspondents as pseudo-id options for the agent."""
    merged = list(correspondents)
    for index, name in enumerate(pending_names):
        merged.append(EntityOption(id=pending_correspondent_id(index), name=name))
    return merged


class AgentDebugTrace(BaseModel):
    """Captured inputs and outputs from a single agent invocation attempt."""

    attempt: int
    prompt: str
    prepared_content_chars: int
    ocr_preview: str
    attachment: AttachmentDebugMetadata | None = None
    available_options: AvailableOptions
    json_schema: dict[str, Any]
    command: list[str] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    output_file_content: str | None = None
    parsed_payload: dict[str, Any] | None = None
    validated_output: CategorizationAgentOutput | None = None
    usage_metadata: AgentUsageMetadata | None = None
    error: str | None = None


class AgentCategorizationResult(BaseModel):
    """Result of an agent categorization attempt."""

    output: CategorizationAgentOutput | None = None
    raw_response: str = ""
    error: str | None = None
    usage_metadata: AgentUsageMetadata | None = None
    debug_traces: list[AgentDebugTrace] = Field(default_factory=list)


class DocumentCategorizer(Protocol):
    """Protocol for agents that categorize documents via LLM."""

    def categorize_document(
        self,
        ocr_content: str,
        available_options: AvailableOptions,
        current_metadata: CurrentMetadata,
        attachment: DocumentAttachment | None = None,
    ) -> AgentCategorizationResult: ...


def build_categorization_json_schema() -> dict[str, Any]:
    """Build a fixed JSON Schema for agent output shape.

    ID validity is enforced post-parse by validate_agent_output() against
    available_options — not duplicated as per-request enums in the schema.
    """
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "content": {"type": ["string", "null"]},
            "document_date": {"type": ["string", "null"]},
            "document_type_id": {"type": ["integer", "null"]},
            "tag_ids": {"type": "array", "items": {"type": "integer"}},
            "correspondent_id": {"type": ["integer", "null"]},
            "new_correspondent_name": {"type": ["string", "null"]},
            "storage_path_id": {"type": ["integer", "null"]},
        },
        "required": [
            "title",
            "content",
            "document_date",
            "document_type_id",
            "tag_ids",
            "correspondent_id",
            "new_correspondent_name",
            "storage_path_id",
        ],
        "additionalProperties": False,
    }
    if schema_uses_forbidden_keywords(schema):
        raise ValueError("Generated schema uses keywords unsupported by CLI structured output")
    return schema


def validate_agent_output(
    output: CategorizationAgentOutput,
    available_options: AvailableOptions,
) -> CategorizationAgentOutput:
    """Validate agent output against available options and business rules."""
    allowed_type_ids = set(available_options.document_type_ids())
    allowed_tag_ids = set(available_options.tag_ids())
    allowed_correspondent_ids = set(available_options.correspondent_ids())
    allowed_storage_path_ids = set(available_options.storage_path_ids())

    if output.document_type_id is not None and output.document_type_id not in allowed_type_ids:
        raise ValueError(f"Invalid document_type_id: {output.document_type_id}")

    if len(output.tag_ids) != len(set(output.tag_ids)):
        raise ValueError("tag_ids must be unique")

    invalid_tags = set(output.tag_ids) - allowed_tag_ids
    if invalid_tags:
        raise ValueError(f"Invalid tag_ids: {sorted(invalid_tags)}")

    if (
        output.correspondent_id is not None
        and output.correspondent_id not in allowed_correspondent_ids
    ):
        raise ValueError(f"Invalid correspondent_id: {output.correspondent_id}")

    if (
        output.storage_path_id is not None
        and output.storage_path_id not in allowed_storage_path_ids
    ):
        raise ValueError(f"Invalid storage_path_id: {output.storage_path_id}")

    if output.new_correspondent_name is not None:
        if output.new_correspondent_name.lower() in available_options.correspondent_names_lower():
            raise ValueError(
                f"new_correspondent_name matches existing correspondent: "
                f"{output.new_correspondent_name!r}"
            )

    return output


def schema_uses_forbidden_keywords(schema: object, forbidden: frozenset[str] | None = None) -> bool:
    """Return True if the schema contains keywords unsupported by CLI structured output."""
    if forbidden is None:
        forbidden = frozenset({"oneOf", "anyOf", "allOf", "not", "if", "then", "else"})

    if isinstance(schema, dict):
        if forbidden.intersection(schema):
            return True
        return any(schema_uses_forbidden_keywords(value, forbidden) for value in schema.values())

    if isinstance(schema, list):
        return any(schema_uses_forbidden_keywords(item, forbidden) for item in schema)

    return False
