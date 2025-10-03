"""Data models for Paperless-ngx API responses."""

from datetime import datetime

from pydantic import BaseModel, Field


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
    owner: int
    user_can_change: bool = True


class CategorizationSuggestion(BaseModel):
    """Claude's categorization suggestion for a document."""

    document_id: int
    current_title: str
    suggested_title: str | None = None
    current_type: int | None = None
    current_type_name: str | None = None
    suggested_type: str | None = None
    suggested_type_id: int | None = None
    current_tags: list[int] = Field(default_factory=list)
    current_tag_names: list[str] = Field(default_factory=list)
    suggested_tags: list[str] = Field(default_factory=list)
    suggested_tag_ids: list[int] = Field(default_factory=list)
    current_correspondent: int | None = None
    current_correspondent_name: str | None = None
    suggested_correspondent: str | None = None
    suggested_correspondent_id: int | None = None
    status: str = "success"
    error_message: str | None = None


class PaginatedResponse(BaseModel):
    """Generic paginated API response."""

    count: int
    next: str | None = None
    previous: str | None = None
    all: list[int] = Field(default_factory=list)
    results: list[dict] = Field(default_factory=list)
