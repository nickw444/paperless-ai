"""Categorization engine that orchestrates document analysis."""

from config.settings import settings
from llm.base import CommandLineAgent
from paperless.client import PaperlessClient
from paperless.models import (
    CategorizationSuggestion,
    Correspondent,
    Document,
    DocumentType,
    StoragePath,
    Tag,
)


class CategorizationEngine:
    """Engine for categorizing documents using LLM agents and Paperless metadata."""

    def __init__(self, agent: CommandLineAgent):
        """Initialize the categorization engine."""
        self.paperless = PaperlessClient()
        self.agent = agent
        self._tags: list[Tag] | None = None
        self._correspondents: list[Correspondent] | None = None
        self._document_types: list[DocumentType] | None = None
        self._storage_paths: list[StoragePath] | None = None
        self.new_entities_found = {
            "correspondents": {},  # name -> list of doc_ids
        }
        self.documents_with_new_entities: set[int] = set()  # Track which docs need re-processing

    def _load_metadata(self):
        """Load and cache all metadata from Paperless."""
        if self._tags is None:
            self._tags = self.paperless.list_tags()
        if self._correspondents is None:
            self._correspondents = self.paperless.list_correspondents()
        if self._document_types is None:
            self._document_types = self.paperless.list_document_types()
        if self._storage_paths is None:
            self._storage_paths = self.paperless.list_storage_paths()

    def _get_protected_tag_ids(self) -> list[int]:
        """Get the IDs of all protected tags configured in settings."""
        protected_tag_ids = []
        protected_tag_names = [name.lower() for name in settings.protected_tags]

        for tag in self._tags:
            if tag.name.lower() in protected_tag_names:
                protected_tag_ids.append(tag.id)

        return protected_tag_ids

    def get_or_create_parsed_tag(self) -> int:
        """Get or create the 'paperless-ai-parsed' tag and return its ID."""
        # Check if it already exists
        for tag in self._tags:
            if tag.name.lower() == "paperless-ai-parsed":
                return tag.id

        # Create it if it doesn't exist
        new_tag = self.paperless.create_tag("paperless-ai-parsed")
        # Invalidate cache and reload to include the new tag
        self._tags = None
        self._load_metadata()
        return new_tag.id

    def categorize_document(self, document: Document) -> CategorizationSuggestion:
        """
        Categorize a single document.

        Args:
            document: The document to categorize

        Returns:
            CategorizationSuggestion with the analysis results

        Note:
            Protected tags configured in settings are ALWAYS preserved if present on the document.
            They will not be passed to the agent and will be automatically included
            in suggested_tag_ids, allowing manual review workflows.
        """
        # Load metadata if not already loaded
        self._load_metadata()

        # Get current metadata names
        current_type_name = self._get_type_name(document.document_type)
        current_tag_names = self._get_tag_names(document.tags)
        current_correspondent_name = self._get_correspondent_name(document.correspondent)
        current_storage_path_name = self._get_storage_path_name(document.storage_path)

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
                current_storage_path=document.storage_path,
                current_storage_path_name=current_storage_path_name,
                status="error",
                error_message="Document has no OCR content",
            )

        # Get available options
        available_types = [t.name for t in self._document_types]
        # Exclude protected tags from available tags - they're always preserved automatically
        protected_tag_ids = self._get_protected_tag_ids()
        available_tags = [t.name for t in self._tags if t.id not in protected_tag_ids]
        available_correspondents = [c.name for c in self._correspondents]

        # Include pending new correspondents from previous documents in this batch
        # This prevents duplicate "NEW: Foo" suggestions for the same correspondent
        pending_new_correspondents = list(self.new_entities_found["correspondents"].keys())
        available_correspondents.extend(pending_new_correspondents)

        available_storage_paths = [sp.name for sp in self._storage_paths]

        # Call the configured agent for categorization
        agent_response = self.agent.categorize_document(
            document.content,
            available_types,
            available_tags,
            available_correspondents,
            available_storage_paths,
        )

        # Handle agent errors
        if agent_response.error:
            return CategorizationSuggestion(
                document_id=document.id,
                current_title=document.title,
                current_type=document.document_type,
                current_type_name=current_type_name,
                current_tags=document.tags,
                current_tag_names=current_tag_names,
                current_correspondent=document.correspondent,
                current_correspondent_name=current_correspondent_name,
                current_storage_path=document.storage_path,
                current_storage_path_name=current_storage_path_name,
                status="error",
                error_message=agent_response.error,
            )

        # Check if correspondent is pending from a previous document in this batch
        correspondent_is_pending = (
            agent_response.correspondent in pending_new_correspondents
            if agent_response.correspondent
            else False
        )

        # Track new entities (only correspondents)
        # Includes ones the agent marked as NEW and ones that matched pending
        # correspondents from previous documents in this batch
        if agent_response.correspondent_is_new and agent_response.correspondent:
            self.new_entities_found["correspondents"].setdefault(
                agent_response.correspondent, []
            ).append(document.id)
            self.documents_with_new_entities.add(document.id)
        elif correspondent_is_pending and agent_response.correspondent:
            # The agent matched a pending correspondent from a previous doc in this batch
            self.new_entities_found["correspondents"][agent_response.correspondent].append(
                document.id
            )
            self.documents_with_new_entities.add(document.id)

        # Map the agent's suggestions to Paperless IDs
        # Only existing entities will have IDs; new entities will be None
        suggested_type_id = (
            self._find_type_id(agent_response.document_type)
            if not agent_response.document_type_is_new
            else None
        )
        suggested_tag_ids = (
            self._find_tag_ids(agent_response.tags_existing or [])
            if agent_response.tags_existing
            else []
        )

        # ALWAYS preserve protected tags if they're currently on the document
        protected_tag_ids = self._get_protected_tag_ids()
        for protected_tag_id in protected_tag_ids:
            if protected_tag_id in document.tags and protected_tag_id not in suggested_tag_ids:
                suggested_tag_ids.append(protected_tag_id)

        if correspondent_is_pending:
            # Treat as new even though the agent didn't mark it as NEW
            # (because we added it to available list from previous docs in batch)
            suggested_correspondent_id = None
            suggested_correspondent_is_new = True
        else:
            suggested_correspondent_id = (
                self._find_correspondent_id(agent_response.correspondent)
                if not agent_response.correspondent_is_new
                else None
            )
            suggested_correspondent_is_new = agent_response.correspondent_is_new

        suggested_storage_path_id = (
            self._find_storage_path_id(agent_response.storage_path)
            if not agent_response.storage_path_is_new
            else None
        )

        return CategorizationSuggestion(
            document_id=document.id,
            current_title=document.title,
            suggested_title=agent_response.title,
            current_type=document.document_type,
            current_type_name=current_type_name,
            suggested_type=agent_response.document_type,
            suggested_type_id=suggested_type_id,
            suggested_type_is_new=agent_response.document_type_is_new,
            current_tags=document.tags,
            current_tag_names=current_tag_names,
            suggested_tags=agent_response.tags or [],
            suggested_tags_existing=agent_response.tags_existing or [],
            suggested_tags_new=agent_response.tags_new or [],
            suggested_tag_ids=suggested_tag_ids,
            current_correspondent=document.correspondent,
            current_correspondent_name=current_correspondent_name,
            suggested_correspondent=agent_response.correspondent,
            suggested_correspondent_id=suggested_correspondent_id,
            suggested_correspondent_is_new=suggested_correspondent_is_new,
            current_storage_path=document.storage_path,
            current_storage_path_name=current_storage_path_name,
            suggested_storage_path=agent_response.storage_path,
            suggested_storage_path_id=suggested_storage_path_id,
            suggested_storage_path_is_new=agent_response.storage_path_is_new,
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

    def _get_storage_path_name(self, storage_path_id: int | None) -> str | None:
        """Get storage path name from ID."""
        if storage_path_id is None:
            return None
        for spath in self._storage_paths:
            if spath.id == storage_path_id:
                return spath.name
        return None

    def _find_storage_path_id(self, storage_path_name: str | None) -> int | None:
        """Find storage path ID by name (case-insensitive)."""
        if not storage_path_name:
            return None
        storage_path_name_lower = storage_path_name.lower()
        for spath in self._storage_paths:
            if spath.name.lower() == storage_path_name_lower:
                return spath.id
        return None
