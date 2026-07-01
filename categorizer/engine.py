"""Categorization engine that orchestrates document analysis."""

from pathlib import Path

from config.settings import settings
from llm.schemas import (
    AgentCategorizationResult,
    AvailableOptions,
    CurrentMetadata,
    DocumentCategorizer,
    EntityOption,
    is_pending_correspondent_id,
    merge_correspondent_options,
    pending_correspondent_name,
)
from paperless.client import PaperlessClient
from paperless.models import (
    CategorizationSuggestion,
    Correspondent,
    Document,
    DocumentType,
    StoragePath,
    Tag,
)

PARSED_TAG_NAME = "paperless-ai-parsed"
FAILED_TAG_NAME = "paperless-ai-failed"
ENGINE_MANAGED_TAG_NAMES = {PARSED_TAG_NAME, FAILED_TAG_NAME}


class CategorizationEngine:
    """Engine for categorizing documents using the Codex agent and Paperless metadata."""

    def __init__(
        self,
        agent: DocumentCategorizer,
        protected_tag_names: list[str] | None = None,
    ):
        """Initialize the categorization engine."""
        self.paperless = PaperlessClient()
        self.agent = agent
        self.protected_tag_names = (
            protected_tag_names
            if protected_tag_names is not None
            else settings.parsed_protected_tags
        )
        self._tags: list[Tag] | None = None
        self._correspondents: list[Correspondent] | None = None
        self._document_types: list[DocumentType] | None = None
        self._storage_paths: list[StoragePath] | None = None
        self.new_entities_found = {
            "correspondents": {},  # name -> list of doc_ids
        }
        self.documents_with_new_entities: set[int] = set()  # Track which docs need re-processing
        self.last_agent_result: AgentCategorizationResult | None = None

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
        """Get IDs for configured protected tags that exist in Paperless."""
        protected_names = {name.lower() for name in self.protected_tag_names}
        if not protected_names:
            return []

        protected_ids = []
        for tag in self._tags:
            if tag.name.lower() in protected_names:
                protected_ids.append(tag.id)
        return protected_ids

    def _get_engine_managed_tag_ids(self) -> list[int]:
        """Get IDs for lifecycle tags managed by paperless-ai itself."""
        managed_ids = []
        for tag in self._tags:
            if tag.name.lower() in ENGINE_MANAGED_TAG_NAMES:
                managed_ids.append(tag.id)
        return managed_ids

    def get_or_create_parsed_tag(self) -> int:
        """Get or create the 'paperless-ai-parsed' tag and return its ID."""
        return self._get_or_create_tag(PARSED_TAG_NAME)

    def get_or_create_failed_tag(self) -> int:
        """Get or create the 'paperless-ai-failed' tag and return its ID."""
        return self._get_or_create_tag(FAILED_TAG_NAME)

    def get_tag_id_by_name(self, name: str) -> int | None:
        """Return the ID for a tag name, if it exists."""
        self._load_metadata()
        name_lower = name.lower()
        for tag in self._tags:
            if tag.name.lower() == name_lower:
                return tag.id
        return None

    def _get_or_create_tag(self, name: str) -> int:
        """Get or create a Paperless tag and return its ID."""
        self._load_metadata()
        name_lower = name.lower()
        # Check if it already exists
        for tag in self._tags:
            if tag.name.lower() == name_lower:
                return tag.id

        # Create it if it doesn't exist
        new_tag = self.paperless.create_tag(name)
        # Invalidate cache and reload to include the new tag
        self._tags = None
        self._load_metadata()
        return new_tag.id

    def _is_tracking_tag(self, tag: Tag) -> bool:
        return tag.name.lower() in {PARSED_TAG_NAME, FAILED_TAG_NAME}

    def categorize_document(self, document: Document) -> CategorizationSuggestion:
        """
        Categorize a single document.

        Args:
            document: The document to categorize

        Returns:
            CategorizationSuggestion with the analysis results

        Note:
            Protected tags configured in settings are ALWAYS preserved if present on the
            document. They will not be passed as available tag options to the agent and
            will be automatically included in suggested_tag_ids. Lifecycle tags managed by
            paperless-ai itself are omitted from the agent context and applied only by the
            engine.
        """
        # Load metadata if not already loaded
        self._load_metadata()

        # Get current metadata names
        current_type_name = self._get_type_name(document.document_type)
        current_tag_names = self._get_tag_names(document.tags)
        current_correspondent_name = self._get_correspondent_name(document.correspondent)
        current_storage_path_name = self._get_storage_path_name(document.storage_path)
        attachment = self.paperless.download_document_attachment(document)

        # Skip only when neither OCR nor a supported source document is available.
        has_ocr_content = bool(document.content and document.content.strip())
        if not has_ocr_content and attachment is None:
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
                error_message="Document has no OCR content or supported attachment",
            )

        pending_new_correspondents = list(self.new_entities_found["correspondents"].keys())
        protected_tag_ids = self._get_protected_tag_ids()
        engine_managed_tag_ids = self._get_engine_managed_tag_ids()
        omitted_tag_ids = set(protected_tag_ids) | set(engine_managed_tag_ids)

        available_options = AvailableOptions(
            document_types=[EntityOption(id=t.id, name=t.name) for t in self._document_types],
            tags=[
                EntityOption(id=t.id, name=t.name)
                for t in self._tags
                if t.id not in omitted_tag_ids
            ],
            correspondents=merge_correspondent_options(
                [EntityOption(id=c.id, name=c.name) for c in self._correspondents],
                pending_new_correspondents,
            ),
            storage_paths=[EntityOption(id=sp.id, name=sp.name) for sp in self._storage_paths],
        )

        current_metadata = CurrentMetadata(
            title=document.title,
            document_type=self._to_entity_option(document.document_type, self._document_types),
            tags=self._get_tag_options(
                [tag_id for tag_id in document.tags if tag_id not in engine_managed_tag_ids]
            ),
            correspondent=self._to_entity_option(document.correspondent, self._correspondents),
            storage_path=self._to_entity_option(document.storage_path, self._storage_paths),
        )

        try:
            result = self.agent.categorize_document(
                document.content,
                available_options,
                current_metadata,
                attachment=attachment,
            )
            self.last_agent_result = result
        finally:
            if attachment:
                Path(attachment.path).unlink(missing_ok=True)

        if result.error or result.output is None:
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
                error_message=result.error or "Agent returned no output",
            )

        output = result.output
        if not has_ocr_content and attachment is not None and output.content is None:
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
                error_message="Document attachment did not provide usable OCR content",
            )

        new_correspondent_name = output.new_correspondent_name

        if new_correspondent_name and not output.correspondent_id:
            self.new_entities_found["correspondents"].setdefault(new_correspondent_name, []).append(
                document.id
            )
            self.documents_with_new_entities.add(document.id)

        suggested_type_id = output.document_type_id
        suggested_type_name = self._get_type_name(suggested_type_id)
        suggested_tag_ids = [
            tag_id for tag_id in output.tag_ids if tag_id not in engine_managed_tag_ids
        ]

        for protected_tag_id in protected_tag_ids:
            if protected_tag_id in document.tags and protected_tag_id not in suggested_tag_ids:
                suggested_tag_ids.append(protected_tag_id)

        if set(document.tags) == set(suggested_tag_ids):
            suggested_tag_ids = list(document.tags)

        if output.correspondent_id is not None:
            if is_pending_correspondent_id(output.correspondent_id):
                pending_name = pending_correspondent_name(
                    output.correspondent_id,
                    pending_new_correspondents,
                )
                suggested_correspondent_id = output.correspondent_id
                suggested_correspondent_name = pending_name
                suggested_correspondent_is_new = True
            else:
                suggested_correspondent_id = output.correspondent_id
                suggested_correspondent_name = self._get_correspondent_name(
                    suggested_correspondent_id
                )
                suggested_correspondent_is_new = False
        elif new_correspondent_name:
            suggested_correspondent_id = None
            suggested_correspondent_name = new_correspondent_name
            suggested_correspondent_is_new = True
        else:
            suggested_correspondent_id = None
            suggested_correspondent_name = None
            suggested_correspondent_is_new = False

        suggested_storage_path_id = output.storage_path_id
        suggested_storage_path_name = self._get_storage_path_name(suggested_storage_path_id)

        suggested_tags = self._get_tag_names(suggested_tag_ids)

        return CategorizationSuggestion(
            document_id=document.id,
            current_title=document.title,
            suggested_title=output.title,
            suggested_content=output.content,
            current_type=document.document_type,
            current_type_name=current_type_name,
            suggested_type=suggested_type_name,
            suggested_type_id=suggested_type_id,
            suggested_type_is_new=False,
            current_tags=document.tags,
            current_tag_names=current_tag_names,
            suggested_tags=suggested_tags,
            suggested_tags_existing=suggested_tags,
            suggested_tags_new=[],
            suggested_tag_ids=suggested_tag_ids,
            current_correspondent=document.correspondent,
            current_correspondent_name=current_correspondent_name,
            suggested_correspondent=suggested_correspondent_name,
            suggested_correspondent_id=suggested_correspondent_id,
            suggested_correspondent_is_new=suggested_correspondent_is_new,
            current_storage_path=document.storage_path,
            current_storage_path_name=current_storage_path_name,
            suggested_storage_path=suggested_storage_path_name,
            suggested_storage_path_id=suggested_storage_path_id,
            suggested_storage_path_is_new=False,
            status="success",
        )

    def find_correspondent_id_by_name(self, name: str) -> int | None:
        """Look up a Paperless correspondent id by name (case-insensitive)."""
        self._load_metadata()
        name_lower = name.lower()
        for correspondent in self._correspondents:
            if correspondent.name.lower() == name_lower:
                return correspondent.id
        return None

    def resolve_suggestion_correspondent_id(self, suggestion) -> int | None:
        """Resolve a suggestion's correspondent to a real Paperless id for applying."""
        correspondent_id = suggestion.suggested_correspondent_id
        if correspondent_id is not None and is_pending_correspondent_id(correspondent_id):
            if suggestion.suggested_correspondent:
                resolved = self.find_correspondent_id_by_name(suggestion.suggested_correspondent)
                if resolved is not None:
                    return resolved

            pending_names = list(self.new_entities_found["correspondents"].keys())
            name = pending_correspondent_name(correspondent_id, pending_names)
            return self.find_correspondent_id_by_name(name) if name else None

        if correspondent_id is not None:
            return correspondent_id

        if suggestion.suggested_correspondent_is_new and suggestion.suggested_correspondent:
            return self.find_correspondent_id_by_name(suggestion.suggested_correspondent)

        return None

    def remove_pending_correspondents(self, names: list[str]) -> None:
        """Remove batch-local pending correspondents after they exist in Paperless."""
        for name in names:
            self.new_entities_found["correspondents"].pop(name, None)

    def has_unresolved_new_correspondent(self, suggestion) -> bool:
        """Return True when a suggestion references a new correspondent not yet in Paperless."""
        if suggestion.status != "success":
            return False
        if not suggestion.suggested_correspondent_is_new:
            return False
        return self.resolve_suggestion_correspondent_id(suggestion) is None

    def _to_entity_option(self, entity_id: int | None, entities) -> EntityOption | None:
        """Map a Paperless entity id to an EntityOption."""
        if entity_id is None:
            return None
        for entity in entities:
            if entity.id == entity_id:
                return EntityOption(id=entity.id, name=entity.name)
        return None

    def _get_tag_options(self, tag_ids: list[int]) -> list[EntityOption]:
        """Get tag EntityOptions from IDs, preserving document order."""
        options: list[EntityOption] = []
        for tag_id in tag_ids:
            for tag in self._tags:
                if tag.id == tag_id:
                    options.append(EntityOption(id=tag.id, name=tag.name))
                    break
        return options

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

    def _get_storage_path_name(self, storage_path_id: int | None) -> str | None:
        """Get storage path name from ID."""
        if storage_path_id is None:
            return None
        for spath in self._storage_paths:
            if spath.id == storage_path_id:
                return spath.name
        return None
