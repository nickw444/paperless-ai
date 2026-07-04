"""Tests for metadata guidance loading and prompt resolution."""

from pathlib import Path

import pytest

from config.metadata_guidance import (
    build_guided_options,
    load_metadata_guidance,
    unknown_guidance_names,
    warn_unknown_guidance_names,
)
from llm.prompts import build_categorization_prompt
from llm.schemas import AvailableOptions, CurrentMetadata, GuidedEntityOption


def test_load_metadata_guidance_parses_tags_document_types_and_storage_paths(tmp_path: Path):
    path = tmp_path / "metadata_guidance.yaml"
    path.write_text(
        """
tags:
  Tax Deduction:
    use_when: Actual deductible expenses
    avoid_when: Routine Tax Invoice bills
document_types:
  Bill:
    use_when: Payment requested
storage_paths:
  Nick:
    use_when: Documents addressed to Nick
    avoid_when: Shared household documents
""".strip(),
        encoding="utf-8",
    )

    guidance = load_metadata_guidance(path)

    assert "tax deduction" in guidance.tags
    assert guidance.tags["tax deduction"].name == "Tax Deduction"
    assert guidance.tags["tax deduction"].entry.use_when == "Actual deductible expenses"
    assert "bill" in guidance.document_types
    assert guidance.document_types["bill"].entry.use_when == "Payment requested"
    assert "nick" in guidance.storage_paths
    assert guidance.storage_paths["nick"].entry.use_when == "Documents addressed to Nick"
    assert guidance.storage_paths["nick"].entry.avoid_when == "Shared household documents"


def test_load_metadata_guidance_returns_empty_when_missing(tmp_path: Path):
    guidance = load_metadata_guidance(tmp_path / "missing.yaml")
    assert guidance.tags == {}
    assert guidance.document_types == {}
    assert guidance.storage_paths == {}


def test_load_metadata_guidance_rejects_invalid_root(tmp_path: Path):
    path = tmp_path / "metadata_guidance.yaml"
    path.write_text("- not a mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be a mapping"):
        load_metadata_guidance(path)


def test_load_metadata_guidance_rejects_invalid_empty_section(tmp_path: Path):
    path = tmp_path / "metadata_guidance.yaml"
    path.write_text("tags: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="section 'tags' must be a mapping"):
        load_metadata_guidance(path)


def test_load_metadata_guidance_allows_null_sections(tmp_path: Path):
    path = tmp_path / "metadata_guidance.yaml"
    path.write_text("tags:\ndocument_types:\n", encoding="utf-8")

    guidance = load_metadata_guidance(path)

    assert guidance.tags == {}
    assert guidance.document_types == {}
    assert guidance.storage_paths == {}


def test_load_metadata_guidance_requires_sectioned_format(tmp_path: Path):
    path = tmp_path / "metadata_guidance.yaml"
    path.write_text("Tax Deduction:\n  use_when: Legacy flat format\n", encoding="utf-8")

    with pytest.raises(ValueError, match="tags.*document_types.*storage_paths"):
        load_metadata_guidance(path)


def test_build_guided_options_matches_available_entities_only():
    guidance = load_metadata_guidance_from_mapping(
        tags={
            "Tax Deduction": {
                "use_when": "Deductible expenses",
                "avoid_when": "Tax Invoice bills",
            },
            "Missing Tag": {
                "use_when": "Never resolved",
            },
        },
        document_types={},
    )

    resolved = build_guided_options(
        [type("Tag", (), {"id": 12, "name": "Tax Deduction"})()],
        guidance.tags,
    )

    assert len(resolved) == 1
    assert resolved[0].id == 12
    assert resolved[0].name == "Tax Deduction"
    assert resolved[0].avoid_when == "Tax Invoice bills"


def test_unknown_guidance_names_reports_missing_paperless_entities():
    guidance = load_metadata_guidance_from_mapping(
        tags={
            "Tax Deduction": {"use_when": "Deductible expenses"},
            "Old Tag": {"use_when": "No longer exists"},
        },
        document_types={},
    )

    unknown = unknown_guidance_names(guidance.tags, ["Tax Deduction", "Utilities"])

    assert unknown == ["Old Tag"]


def test_warn_unknown_guidance_names_prints_warning(capsys, tmp_path: Path):
    guidance = load_metadata_guidance_from_mapping(
        tags={"Stale Tag": {"use_when": "Gone"}},
        document_types={},
    )

    warn_unknown_guidance_names(
        guidance.tags,
        ["Utilities"],
        path=tmp_path / "metadata_guidance.yaml",
        label="tags",
    )

    captured = capsys.readouterr()
    assert "Stale Tag" in captured.err
    assert "metadata_guidance.yaml" in captured.err


def test_warn_unknown_storage_path_guidance_names_prints_warning(capsys, tmp_path: Path):
    guidance = load_metadata_guidance_from_mapping(
        tags={},
        document_types={},
        storage_paths={"Old Person": {"use_when": "No longer exists"}},
    )

    warn_unknown_guidance_names(
        guidance.storage_paths,
        ["Nick"],
        path=tmp_path / "metadata_guidance.yaml",
        label="storage_paths",
    )

    captured = capsys.readouterr()
    assert "Old Person" in captured.err
    assert "storage_paths" in captured.err


def test_build_categorization_prompt_embeds_guidance_in_available_options():
    prompt = build_categorization_prompt(
        content="Invoice total $42",
        available_options=AvailableOptions(
            tags=[
                GuidedEntityOption(
                    id=12,
                    name="Tax Deduction",
                    use_when="Deductible expenses",
                    avoid_when="Tax Invoice bills",
                )
            ]
        ),
        current_metadata=CurrentMetadata(title="scan.pdf"),
    )

    assert "<tag_guidance>" not in prompt
    assert '"use_when":"Deductible expenses"' in prompt
    assert '"avoid_when":"Tax Invoice bills"' in prompt
    assert "Only tags listed in available_options.tags may be used" in prompt


def test_build_categorization_prompt_embeds_storage_path_guidance_in_available_options():
    prompt = build_categorization_prompt(
        content="Dear Nick, your statement is ready",
        available_options=AvailableOptions(
            storage_paths=[
                GuidedEntityOption(
                    id=31,
                    name="Nick",
                    use_when="Documents addressed to Nick",
                    avoid_when="Documents addressed to someone else",
                )
            ]
        ),
        current_metadata=CurrentMetadata(title="scan.pdf"),
    )

    assert '"storage_paths":[{"id":31,"name":"Nick"' in prompt
    assert '"use_when":"Documents addressed to Nick"' in prompt
    assert "available_options.storage_paths may be used" in prompt


def load_metadata_guidance_from_mapping(
    *,
    tags: dict,
    document_types: dict | None = None,
    storage_paths: dict | None = None,
):
    from config.metadata_guidance import MetadataGuidance, _parse_guidance_section

    return MetadataGuidance(
        tags=_parse_guidance_section(
            tags,
            path=Path("metadata_guidance.yaml"),
            section_name="tags",
        ),
        document_types=_parse_guidance_section(
            document_types or {},
            path=Path("metadata_guidance.yaml"),
            section_name="document_types",
        ),
        storage_paths=_parse_guidance_section(
            storage_paths or {},
            path=Path("metadata_guidance.yaml"),
            section_name="storage_paths",
        ),
    )
