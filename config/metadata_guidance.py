"""Load and resolve metadata guidance for tags, document types, and storage paths."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from llm.schemas import GuidedEntityOption


class GuidanceEntry(BaseModel):
    """Usage instructions for a Paperless metadata entity."""

    use_when: str | None = None
    avoid_when: str | None = None

    def has_guidance(self) -> bool:
        use_when = self.use_when and self.use_when.strip()
        avoid_when = self.avoid_when and self.avoid_when.strip()
        return bool(use_when or avoid_when)


class ConfiguredGuidance(BaseModel):
    """A configured entity name paired with usage instructions."""

    name: str
    entry: GuidanceEntry


class MetadataGuidance(BaseModel):
    """Metadata guidance configured for agent prompts."""

    tags: dict[str, ConfiguredGuidance] = Field(default_factory=dict)
    document_types: dict[str, ConfiguredGuidance] = Field(default_factory=dict)
    storage_paths: dict[str, ConfiguredGuidance] = Field(default_factory=dict)


class NamedEntity(Protocol):
    id: int
    name: str


def load_metadata_guidance_from_mapping(
    raw: dict,
    *,
    path: Path,
) -> MetadataGuidance:
    """Load metadata guidance from a config mapping."""
    if "tags" not in raw and "document_types" not in raw and "storage_paths" not in raw:
        raise ValueError(
            f"Metadata guidance must contain 'tags', 'document_types', "
            f"and/or 'storage_paths' sections: {path}"
        )

    return MetadataGuidance(
        tags=_parse_guidance_section(raw.get("tags", {}), path=path, section_name="tags"),
        document_types=_parse_guidance_section(
            raw.get("document_types", {}),
            path=path,
            section_name="document_types",
        ),
        storage_paths=_parse_guidance_section(
            raw.get("storage_paths", {}),
            path=path,
            section_name="storage_paths",
        ),
    )


def _parse_guidance_section(
    section: object,
    *,
    path: Path,
    section_name: str,
) -> dict[str, ConfiguredGuidance]:
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ValueError(f"Metadata guidance section '{section_name}' must be a mapping: {path}")

    guidance: dict[str, ConfiguredGuidance] = {}
    for entity_name, entry_data in section.items():
        if not isinstance(entity_name, str) or not entity_name.strip():
            raise ValueError(
                f"Metadata guidance '{section_name}' keys must be non-empty strings: {path}"
            )
        if entry_data is None:
            continue
        if not isinstance(entry_data, dict):
            raise ValueError(
                f"Metadata guidance for '{section_name}.{entity_name}' must be a mapping: {path}"
            )

        entry = GuidanceEntry.model_validate(entry_data)
        if entry.has_guidance():
            normalized_name = entity_name.strip()
            guidance[normalized_name.lower()] = ConfiguredGuidance(
                name=normalized_name,
                entry=entry,
            )

    return guidance


def build_guided_options(
    entities: list[NamedEntity],
    guidance_by_name: dict[str, ConfiguredGuidance],
) -> list[GuidedEntityOption]:
    """Return only entities documented in guidance, with rules embedded."""
    from llm.schemas import GuidedEntityOption

    if not guidance_by_name:
        return []

    guided: list[GuidedEntityOption] = []
    for entity in entities:
        configured = guidance_by_name.get(entity.name.lower())
        if configured is None:
            continue
        entry = configured.entry
        guided.append(
            GuidedEntityOption(
                id=entity.id,
                name=entity.name,
                use_when=entry.use_when.strip() if entry.use_when else None,
                avoid_when=entry.avoid_when.strip() if entry.avoid_when else None,
            )
        )

    return sorted(guided, key=lambda item: item.name.lower())


def unknown_guidance_names(
    guidance_by_name: dict[str, ConfiguredGuidance],
    entity_names: list[str],
) -> list[str]:
    """Return configured guidance names that do not exist in Paperless."""
    paperless_names = {name.lower() for name in entity_names}
    return sorted(
        configured.name
        for configured in guidance_by_name.values()
        if configured.name.lower() not in paperless_names
    )


def warn_unknown_guidance_names(
    guidance_by_name: dict[str, ConfiguredGuidance],
    entity_names: list[str],
    *,
    path: Path,
    label: str,
) -> None:
    """Print a warning for configured names missing from Paperless."""
    unknown = unknown_guidance_names(guidance_by_name, entity_names)
    if not unknown:
        return

    joined = ", ".join(f"'{name}'" for name in unknown)
    print(
        f"Warning: {label} in {path} references unknown Paperless entities: {joined}",
        file=sys.stderr,
    )
