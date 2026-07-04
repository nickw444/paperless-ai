"""Tests for metadata guidance loading and prompt resolution."""

from pathlib import Path

import pytest

from config.metadata_guidance import (
    build_guided_options,
    load_metadata_guidance_from_mapping,
    unknown_guidance_names,
    warn_unknown_guidance_names,
)
from llm.prompts import build_categorization_prompt
from llm.schemas import AvailableOptions, CurrentMetadata, GuidedEntityOption


def test_load_metadata_guidance_parses_tags_document_types_and_storage_paths():
    guidance = load_metadata_guidance_from_mapping(
        {
            "tags": {
                "Tax Deduction": {
                    "use_when": "Actual deductible expenses",
                    "avoid_when": "Routine Tax Invoice bills",
                },
            },
            "document_types": {
                "Bill": {
                    "use_when": "Payment requested",
                },
            },
            "storage_paths": {
                "Nick": {
                    "use_when": "Documents addressed to Nick",
                    "avoid_when": "Shared household documents",
                },
            },
        },
        path=Path("config.yaml"),
    )

    assert "tax deduction" in guidance.tags
    assert guidance.tags["tax deduction"].name == "Tax Deduction"
    assert guidance.tags["tax deduction"].entry.use_when == "Actual deductible expenses"
    assert "bill" in guidance.document_types
    assert guidance.document_types["bill"].entry.use_when == "Payment requested"
    assert "nick" in guidance.storage_paths
    assert guidance.storage_paths["nick"].entry.use_when == "Documents addressed to Nick"
    assert guidance.storage_paths["nick"].entry.avoid_when == "Shared household documents"


def test_load_metadata_guidance_rejects_invalid_empty_section():
    with pytest.raises(ValueError, match="section 'tags' must be a mapping"):
        load_metadata_guidance_from_mapping({"tags": []}, path=Path("config.yaml"))


def test_load_metadata_guidance_allows_null_sections():
    guidance = load_metadata_guidance_from_mapping(
        {"tags": None, "document_types": None, "storage_paths": None},
        path=Path("config.yaml"),
    )

    assert guidance.tags == {}
    assert guidance.document_types == {}
    assert guidance.storage_paths == {}


def test_load_metadata_guidance_requires_sectioned_format():
    with pytest.raises(ValueError, match="tags.*document_types.*storage_paths"):
        load_metadata_guidance_from_mapping(
            {"Tax Deduction": {"use_when": "Deductible expenses"}},
            path=Path("config.yaml"),
        )


def test_build_guided_options_matches_available_entities_only():
    guidance = build_metadata_guidance(
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
    guidance = build_metadata_guidance(
        tags={
            "Tax Deduction": {"use_when": "Deductible expenses"},
            "Old Tag": {"use_when": "No longer exists"},
        },
        document_types={},
    )

    unknown = unknown_guidance_names(guidance.tags, ["Tax Deduction", "Utilities"])

    assert unknown == ["Old Tag"]


def test_warn_unknown_guidance_names_prints_warning(capsys, tmp_path: Path):
    guidance = build_metadata_guidance(
        tags={"Stale Tag": {"use_when": "Gone"}},
        document_types={},
    )

    warn_unknown_guidance_names(
        guidance.tags,
        ["Utilities"],
        path=tmp_path / "config.yaml",
        label="tags",
    )

    captured = capsys.readouterr()
    assert "Stale Tag" in captured.err
    assert "config.yaml" in captured.err


def test_warn_unknown_storage_path_guidance_names_prints_warning(capsys, tmp_path: Path):
    guidance = build_metadata_guidance(
        tags={},
        document_types={},
        storage_paths={"Old Person": {"use_when": "No longer exists"}},
    )

    warn_unknown_guidance_names(
        guidance.storage_paths,
        ["Nick"],
        path=tmp_path / "config.yaml",
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


def build_metadata_guidance(
    *,
    tags: dict,
    document_types: dict | None = None,
    storage_paths: dict | None = None,
):
    from config.metadata_guidance import load_metadata_guidance_from_mapping as load_guidance

    return load_guidance(
        {
            "tags": tags,
            "document_types": document_types or {},
            "storage_paths": storage_paths or {},
        },
        path=Path("config.yaml"),
    )
