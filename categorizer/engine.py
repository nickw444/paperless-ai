"""Categorization engine that orchestrates document analysis."""

from claude.cli import ClaudeClient
from paperless.client import PaperlessClient
from paperless.models import (
    CategorizationSuggestion,
    Correspondent,
    Document,
    DocumentType,
    Tag,
)


class CategorizationEngine:
    """Engine for categorizing documents using Claude and Paperless metadata."""

    def __init__(self):
        """Initialize the categorization engine."""
        self.paperless = PaperlessClient()
        self.claude = ClaudeClient()
        self._tags: list[Tag] | None = None
        self._correspondents: list[Correspondent] | None = None
        self._document_types: list[DocumentType] | None = None

    def _load_metadata(self):
        """Load and cache all metadata from Paperless."""
        if self._tags is None:
            self._tags = self.paperless.list_tags()
        if self._correspondents is None:
            self._correspondents = self.paperless.list_correspondents()
        if self._document_types is None:
            self._document_types = self.paperless.list_document_types()

    def categorize_document(self, document: Document) -> CategorizationSuggestion:
        """
        Categorize a single document.

        Args:
            document: The document to categorize

        Returns:
            CategorizationSuggestion with the analysis results
        """
        # Load metadata if not already loaded
        self._load_metadata()

        # Get current metadata names
        current_type_name = self._get_type_name(document.document_type)
        current_tag_names = self._get_tag_names(document.tags)
        current_correspondent_name = self._get_correspondent_name(document.correspondent)

        # Skip if document has no content
        if not document.content or not document.content.strip():
            return CategorizationSuggestion(
                document_id=document.id,
                current_title=document.title,
                current_type=document.document_type,
                current_type_name=current_type_name,
                current_tags=document.tags,
                current_tag_names=current_tag_names,
                current_correspondent=document.correspondent,
                current_correspondent_name=current_correspondent_name,
                status="error",
                error_message="Document has no OCR content",
            )

        # Get available options
        available_types = [t.name for t in self._document_types]
        available_tags = [t.name for t in self._tags]
        available_correspondents = [c.name for c in self._correspondents]

        # Call Claude for categorization
        claude_response = self.claude.categorize_document(
            document.content, available_types, available_tags, available_correspondents
        )

        # Handle Claude errors
        if claude_response.error:
            return CategorizationSuggestion(
                document_id=document.id,
                current_title=document.title,
                current_type=document.document_type,
                current_type_name=current_type_name,
                current_tags=document.tags,
                current_tag_names=current_tag_names,
                current_correspondent=document.correspondent,
                current_correspondent_name=current_correspondent_name,
                status="error",
                error_message=claude_response.error,
            )

        # Map Claude's suggestions to Paperless IDs
        suggested_type_id = self._find_type_id(claude_response.document_type)
        suggested_tag_ids = self._find_tag_ids(claude_response.tags or [])
        suggested_correspondent_id = self._find_correspondent_id(claude_response.correspondent)

        return CategorizationSuggestion(
            document_id=document.id,
            current_title=document.title,
            suggested_title=claude_response.title,
            current_type=document.document_type,
            current_type_name=current_type_name,
            suggested_type=claude_response.document_type,
            suggested_type_id=suggested_type_id,
            current_tags=document.tags,
            current_tag_names=current_tag_names,
            suggested_tags=claude_response.tags or [],
            suggested_tag_ids=suggested_tag_ids,
            current_correspondent=document.correspondent,
            current_correspondent_name=current_correspondent_name,
            suggested_correspondent=claude_response.correspondent,
            suggested_correspondent_id=suggested_correspondent_id,
            status="success",
        )

    def _get_type_name(self, type_id: int | None) -> str | None:
        """Get document type name from ID."""
        if type_id is None:
            return None
        for dt in self._document_types:
            if dt.id == type_id:
                return dt.name
        return None

    def _get_tag_names(self, tag_ids: list[int]) -> list[str]:
        """Get tag names from IDs."""
        names = []
        for tag_id in tag_ids:
            for tag in self._tags:
                if tag.id == tag_id:
                    names.append(tag.name)
                    break
        return names

    def _get_correspondent_name(self, correspondent_id: int | None) -> str | None:
        """Get correspondent name from ID."""
        if correspondent_id is None:
            return None
        for corr in self._correspondents:
            if corr.id == correspondent_id:
                return corr.name
        return None

    def _find_type_id(self, type_name: str | None) -> int | None:
        """Find document type ID by name (case-insensitive)."""
        if not type_name:
            return None
        type_name_lower = type_name.lower()
        for dt in self._document_types:
            if dt.name.lower() == type_name_lower:
                return dt.id
        return None

    def _find_tag_ids(self, tag_names: list[str]) -> list[int]:
        """Find tag IDs by names (case-insensitive)."""
        tag_ids = []
        for tag_name in tag_names:
            tag_name_lower = tag_name.lower()
            for tag in self._tags:
                if tag.name.lower() == tag_name_lower:
                    tag_ids.append(tag.id)
                    break
        return tag_ids

    def _find_correspondent_id(self, correspondent_name: str | None) -> int | None:
        """Find correspondent ID by name (case-insensitive)."""
        if not correspondent_name:
            return None
        correspondent_name_lower = correspondent_name.lower()
        for corr in self._correspondents:
            if corr.name.lower() == correspondent_name_lower:
                return corr.id
        return None
