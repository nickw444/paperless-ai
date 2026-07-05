"""Categorization engine that orchestrates document analysis."""

import json
import os
from pathlib import Path
from typing import Any

from config.metadata_guidance import (
    build_guided_options,
    warn_unknown_guidance_names,
)
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
    CustomField,
    Document,
    DocumentType,
    ProcessingMetadata,
    StoragePath,
    Tag,
)

PARSED_TAG_NAME = "paperless-ai-parsed"
FAILED_TAG_NAME = "paperless-ai-failed"
ENGINE_MANAGED_TAG_NAMES = {PARSED_TAG_NAME, FAILED_TAG_NAME}
PROCESSING_VERSION_FIELD_NAME = "paperless-ai-version"
PROCESSING_MODEL_FIELD_NAME = "paperless-ai-model"
PROCESSING_TOKENS_FIELD_NAME = "paperless-ai-tokens"


class CategorizationEngine:
    """Engine for categorizing documents using the Codex agent and Paperless metadata."""

    def __init__(
        self,
        agent: DocumentCategorizer,
    ):
        """Initialize the categorization engine."""
        self.paperless = PaperlessClient()
        self.agent = agent
        self._tags: list[Tag] | None = None
        self._correspondents: list[Correspondent] | None = None
        self._document_types: list[DocumentType] | None = None
        self._storage_paths: list[StoragePath] | None = None
        self._custom_fields: list[CustomField] | None = None
        self.new_entities_found = {
            "correspondents": {},  # name -> list of doc_ids
        }
        self.documents_with_new_entities: set[int] = set()  # Track which docs need re-processing
        self.last_agent_result: AgentCategorizationResult | None = None
        metadata_guidance = self._load_metadata_guidance()
        self._tag_guidance_by_name = metadata_guidance.tags
        self._document_type_guidance_by_name = metadata_guidance.document_types
        self._storage_path_guidance_by_name = metadata_guidance.storage_paths
        self._guidance_warned = False

    def _guidance_path(self) -> Path:
        return Path.cwd() / os.environ.get("PAPERLESS_AI_CONFIG_FILE", "config.yaml")

    def _load_metadata_guidance(self):
        return settings.metadata_guidance

    def _warn_unknown_guidance(self) -> None:
        if self._guidance_warned:
            return

        path = self._guidance_path()

        if self._tag_guidance_by_name:
            warn_unknown_guidance_names(
                self._tag_guidance_by_name,
                [tag.name for tag in self._tags],
                path=path,
                label="tags",
            )

        if self._document_type_guidance_by_name:
            warn_unknown_guidance_names(
                self._document_type_guidance_by_name,
                [document_type.name for document_type in self._document_types],
                path=path,
                label="document_types",
            )

        if self._storage_path_guidance_by_name:
            warn_unknown_guidance_names(
                self._storage_path_guidance_by_name,
                [storage_path.name for storage_path in self._storage_paths],
                path=path,
                label="storage_paths",
            )

        self._guidance_warned = True

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
        self._warn_unknown_guidance()

    def _load_custom_fields(self) -> None:
        """Load and cache custom fields from Paperless."""
        if self._custom_fields is None:
            self._custom_fields = self.paperless.list_custom_fields()

    def _get_protected_tag_ids(self) -> list[int]:
        """Get IDs for guided tags that can be added by the agent but not removed."""
        protected_names = {
            configured.name.lower()
            for configured in self._tag_guidance_by_name.values()
            if configured.entry.protected
        }
        if not protected_names:
            return []

        protected_ids = []
        for tag in self._tags:
            if tag.name.lower() in protected_names:
                protected_ids.append(tag.id)
        return protected_ids

    def _get_deprecated_tag_ids(self) -> list[int]:
        """Get IDs for guided tags that should be removed when omitted."""
        deprecated_names = {
            configured.name.lower()
            for configured in self._tag_guidance_by_name.values()
            if configured.entry.deprecated
        }
        if not deprecated_names:
            return []

        deprecated_ids = []
        for tag in self._tags:
            if tag.name.lower() in deprecated_names:
                deprecated_ids.append(tag.id)
        return deprecated_ids

    def _get_engine_managed_tag_ids(self) -> list[int]:
        """Get IDs for lifecycle tags managed by paperless-ai itself."""
        managed_ids = []
        for tag in self._tags:
            if self._is_tracking_tag(tag):
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

    def get_or_create_processing_custom_fields(self) -> dict[str, int]:
        """Return IDs for paperless-ai processing custom fields, creating missing ones."""
        return self._processing_custom_field_ids(create=True)

    def get_processing_version_custom_field_id(self) -> int | None:
        """Return the backfill comparison marker custom field ID if it exists."""
        return self._processing_custom_field_ids(create=False).get("version")

    def processing_metadata_for_result(
        self,
        result: AgentCategorizationResult,
    ) -> ProcessingMetadata:
        """Build custom-field metadata for a successful categorization result."""
        usage = result.usage_metadata
        model = usage.model if usage and usage.model else settings.codex.model
        return ProcessingMetadata(
            version=settings.processing.backfill_comparison_version,
            model=model,
            tokens=_format_token_metadata_json(usage),
        )

    def processing_custom_field_values(
        self,
        metadata: ProcessingMetadata | None,
    ) -> list[dict[str, int | str]]:
        """Map processing metadata to Paperless custom field id/value payload."""
        if metadata is None:
            return []

        field_ids = self.get_or_create_processing_custom_fields()
        values = [
            {"field": field_ids["version"], "value": metadata.version},
        ]
        if metadata.model:
            values.append({"field": field_ids["model"], "value": metadata.model})
        if metadata.tokens:
            values.append({"field": field_ids["tokens"], "value": metadata.tokens})
        return values

    def is_document_processing_stale(
        self,
        document: Document,
        version_field_id: int | None = None,
    ) -> bool:
        """Return whether a document's stored backfill comparison marker differs from config."""
        field_id = version_field_id
        if field_id is None:
            field_id = self.get_processing_version_custom_field_id()
        if field_id is None:
            return True
        return (
            _document_custom_field_value(document.custom_fields, field_id)
            != settings.processing.backfill_comparison_version
        )

    def categorize_document(self, document: Document) -> CategorizationSuggestion:
        """
        Categorize a single document.

        Args:
            document: The document to categorize

        Returns:
            CategorizationSuggestion with the analysis results

        Note:
            Only guided tags are managed by the agent. Unguided tags are omitted from
            the agent context and preserved if present on the document. Guided tags
            marked protected remain available to the agent so they can be added, but
            are also preserved when already present. Lifecycle tags managed by
            paperless-ai itself are omitted from the agent context and applied only by
            the engine.
        """
        # Load metadata if not already loaded
        self._load_metadata()

        engine_managed_tag_ids = self._get_engine_managed_tag_ids()
        current_user_tag_ids = self._filter_engine_managed_tag_ids(
            document.tags,
            engine_managed_tag_ids,
        )

        # Get current metadata names
        current_type_name = self._get_type_name(document.document_type)
        current_tag_names = self._get_tag_names(current_user_tag_ids)
        current_correspondent_name = self._get_correspondent_name(document.correspondent)
        current_storage_path_name = self._get_storage_path_name(document.storage_path)
        attachment = self.paperless.download_document_attachment(document)

        # Skip only when neither OCR nor a supported source document is available.
        has_ocr_content = bool(document.content and document.content.strip())
        if not has_ocr_content and attachment is None:
            return CategorizationSuggestion(
                document_id=document.id,
                current_title=document.title,
                current_document_date=document.created_date,
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
        deprecated_tag_ids = set(self._get_deprecated_tag_ids())
        omitted_tag_ids = set(engine_managed_tag_ids)

        available_options = AvailableOptions(
            document_types=build_guided_options(
                self._document_types,
                self._document_type_guidance_by_name,
            ),
            tags=build_guided_options(
                [tag for tag in self._tags if tag.id not in omitted_tag_ids],
                self._tag_guidance_by_name,
            ),
            correspondents=merge_correspondent_options(
                [EntityOption(id=c.id, name=c.name) for c in self._correspondents],
                pending_new_correspondents,
            ),
            storage_paths=build_guided_options(
                self._storage_paths,
                self._storage_path_guidance_by_name,
            ),
        )
        visible_document_type_ids = set(available_options.document_type_ids())
        visible_tag_ids = set(available_options.tag_ids())
        current_visible_tag_ids = [
            tag_id for tag_id in current_user_tag_ids if tag_id in visible_tag_ids
        ]
        current_unmanaged_tag_ids = [
            tag_id for tag_id in current_user_tag_ids if tag_id not in visible_tag_ids
        ]

        current_metadata = CurrentMetadata(
            title=document.title,
            document_date=document.created_date,
            document_type=(
                self._to_entity_option(document.document_type, self._document_types)
                if document.document_type in visible_document_type_ids
                else None
            ),
            tags=self._get_tag_options(current_visible_tag_ids),
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
                current_document_date=document.created_date,
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
                processing_metadata=self.processing_metadata_for_result(result),
            )

        output = result.output
        if not has_ocr_content and attachment is not None and output.content is None:
            return CategorizationSuggestion(
                document_id=document.id,
                current_title=document.title,
                current_document_date=document.created_date,
                current_type=document.document_type,
                current_type_name=current_type_name,
                current_tags=document.tags,
                current_tag_names=current_tag_names,
                current_correspondent=document.correspondent,
                current_correspondent_name=current_correspondent_name,
                current_storage_path=document.storage_path,
                current_storage_path_name=current_storage_path_name,
                status="error",
                error_message="Document attachment did not provide usable content",
                processing_metadata=self.processing_metadata_for_result(result),
            )

        new_correspondent_name = output.new_correspondent_name

        if new_correspondent_name and not output.correspondent_id:
            self.new_entities_found["correspondents"].setdefault(new_correspondent_name, []).append(
                document.id
            )
            self.documents_with_new_entities.add(document.id)

        suggested_type_id = output.document_type_id
        suggested_type_name = self._get_type_name(suggested_type_id)
        suggested_tag_ids = self._filter_engine_managed_tag_ids(
            output.tag_ids,
            engine_managed_tag_ids,
        )

        for unmanaged_tag_id in current_unmanaged_tag_ids:
            if (
                unmanaged_tag_id not in deprecated_tag_ids
                and unmanaged_tag_id not in suggested_tag_ids
            ):
                suggested_tag_ids.append(unmanaged_tag_id)

        for protected_tag_id in protected_tag_ids:
            if (
                protected_tag_id not in deprecated_tag_ids
                and protected_tag_id in document.tags
                and protected_tag_id not in suggested_tag_ids
            ):
                suggested_tag_ids.append(protected_tag_id)

        if set(current_user_tag_ids) == set(suggested_tag_ids):
            suggested_tag_ids = list(current_user_tag_ids)

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
            current_document_date=document.created_date,
            suggested_document_date=(
                output.document_date.isoformat() if output.document_date is not None else None
            ),
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
            processing_metadata=self.processing_metadata_for_result(result),
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

    def _processing_custom_field_ids(self, *, create: bool) -> dict[str, int]:
        self._load_custom_fields()
        names = {
            "version": PROCESSING_VERSION_FIELD_NAME,
            "model": PROCESSING_MODEL_FIELD_NAME,
            "tokens": PROCESSING_TOKENS_FIELD_NAME,
        }
        field_ids: dict[str, int] = {}
        fields_by_name = {field.name.lower(): field for field in self._custom_fields}

        for key, name in names.items():
            field = fields_by_name.get(name.lower())
            if field is None:
                if not create:
                    continue
                created = False
                try:
                    field = self.paperless.create_custom_field(name, data_type="string")
                    created = True
                except ValueError as error:
                    if "custom field with this name already exists" not in str(error).lower():
                        raise
                    self._custom_fields = None
                    self._load_custom_fields()
                    fields_by_name = {field.name.lower(): field for field in self._custom_fields}
                    field = fields_by_name.get(name.lower())
                    if field is None:
                        raise
                if created:
                    self._custom_fields.append(field)
                    fields_by_name[field.name.lower()] = field
            field_ids[key] = field.id

        return field_ids

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

    def _filter_engine_managed_tag_ids(
        self,
        tag_ids: list[int],
        engine_managed_tag_ids: list[int],
    ) -> list[int]:
        """Remove lifecycle tag IDs while preserving tag order."""
        managed_ids = set(engine_managed_tag_ids)
        return [tag_id for tag_id in tag_ids if tag_id not in managed_ids]

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


def _format_token_metadata_json(usage) -> str | None:
    if usage is None:
        return None

    tokens: dict[str, int] = {}
    if usage.total_tokens is not None:
        tokens["total"] = usage.total_tokens
    if usage.input_tokens is not None:
        tokens["input"] = usage.input_tokens
    if usage.output_tokens is not None:
        tokens["output"] = usage.output_tokens

    if not tokens:
        return None
    return json.dumps(tokens, separators=(",", ":"))


def _document_custom_field_value(
    custom_fields: list[dict[str, Any]] | dict[str, Any],
    field_id: int,
) -> Any:
    """Extract a Paperless document custom field value from common API shapes."""
    field_id_string = str(field_id)
    if isinstance(custom_fields, dict):
        return custom_fields.get(field_id_string, custom_fields.get(field_id))

    for item in custom_fields:
        item_field_id = item.get("field")
        if isinstance(item_field_id, dict):
            item_field_id = item_field_id.get("id")
        if item_field_id is None:
            item_field_id = item.get("id")
        if str(item_field_id) == field_id_string:
            return item.get("value")
    return None
