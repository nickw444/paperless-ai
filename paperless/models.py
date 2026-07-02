"""Data models for Paperless-ngx API responses."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Tag(BaseModel):
    """Paperless tag model."""

    id: int
    name: str
    slug: str
    color: str = "#000000"
    text_color: str = "#ffffff"
    match: str = ""
    matching_algorithm: int = 0
    is_inbox_tag: bool = False
    document_count: int = 0


class Correspondent(BaseModel):
    """Paperless correspondent model."""

    id: int
    name: str
    slug: str
    match: str = ""
    matching_algorithm: int = 0
    is_insensitive: bool = True
    document_count: int = 0


class DocumentType(BaseModel):
    """Paperless document type model."""

    id: int
    name: str
    slug: str
    match: str = ""
    matching_algorithm: int = 0
    is_insensitive: bool = True
    document_count: int = 0


class StoragePath(BaseModel):
    """Paperless storage path model."""

    id: int
    name: str
    slug: str
    path: str
    match: str = ""
    matching_algorithm: int = 0
    is_insensitive: bool = True
    document_count: int = 0


class CustomField(BaseModel):
    """Paperless custom field definition."""

    id: int
    name: str
    data_type: str = "string"
    extra_data: dict[str, Any] = Field(default_factory=dict)
    document_count: int = 0

    @field_validator("extra_data", mode="before")
    @classmethod
    def default_extra_data(cls, value):
        """Paperless may return null for custom fields without extra data."""
        return {} if value is None else value


class ProcessingMetadata(BaseModel):
    """paperless-ai processing metadata written to Paperless custom fields."""

    version: str
    model: str | None = None
    tokens: str | None = None


class Document(BaseModel):
    """Paperless document model."""

    id: int
    title: str
    content: str = ""
    correspondent: int | None = None
    document_type: int | None = None
    storage_path: int | None = None
    tags: list[int] = Field(default_factory=list)
    created: datetime
    created_date: str
    modified: datetime
    added: datetime
    archive_serial_number: int | None = None
    original_file_name: str
    archived_file_name: str | None = None
    mime_type: str | None = None
    page_count: int | None = None
    owner: int | None = None
    user_can_change: bool = True
    custom_fields: list[dict[str, Any]] | dict[str, Any] = Field(default_factory=list)


class DocumentAttachment(BaseModel):
    """Downloaded document file supplied to the categorization agent."""

    path: str
    source: str
    mime_type: str
    filename: str
    byte_size: int | None = None


class CategorizationSuggestion(BaseModel):
    """AI agent categorization suggestion for a document."""

    document_id: int
    current_title: str
    suggested_title: str | None = None
    suggested_content: str | None = None
    current_document_date: str | None = None
    suggested_document_date: str | None = None
    current_type: int | None = None
    current_type_name: str | None = None
    suggested_type: str | None = None
    suggested_type_id: int | None = None
    suggested_type_is_new: bool = False
    current_tags: list[int] = Field(default_factory=list)
    current_tag_names: list[str] = Field(default_factory=list)
    suggested_tags: list[str] = Field(default_factory=list)
    suggested_tags_existing: list[str] = Field(default_factory=list)
    suggested_tags_new: list[str] = Field(default_factory=list)
    suggested_tag_ids: list[int] = Field(default_factory=list)
    current_correspondent: int | None = None
    current_correspondent_name: str | None = None
    suggested_correspondent: str | None = None
    suggested_correspondent_id: int | None = None
    suggested_correspondent_is_new: bool = False
    current_storage_path: int | None = None
    current_storage_path_name: str | None = None
    suggested_storage_path: str | None = None
    suggested_storage_path_id: int | None = None
    suggested_storage_path_is_new: bool = False
    status: str = "success"
    error_message: str | None = None
    processing_metadata: ProcessingMetadata | None = None


class PaginatedResponse(BaseModel):
    """Generic paginated API response."""

    count: int
    next: str | None = None
    previous: str | None = None
    all: list[int] = Field(default_factory=list)
    results: list[dict] = Field(default_factory=list)
