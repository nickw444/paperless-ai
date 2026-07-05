"""Tests for application settings parsing."""

from pathlib import Path

import pytest

from config.settings import AttachmentSettings, Settings, load_settings


def test_supported_attachment_mime_types_are_normalized_from_yaml_list():
    settings = AttachmentSettings(
        supported_mime_types=[" application/pdf ", "IMAGE/PNG", ""],
    )

    assert settings.supported_mime_types == ["application/pdf", "image/png"]


def test_backfill_comparison_version_defaults_to_initial_marker():
    settings = Settings(
        paperless={
            "url": "http://paperless.example",
            "api_token": "token",
        },
    )

    assert settings.processing.backfill_comparison_version == "1"


def test_backfill_comparison_version_can_be_overridden():
    settings = Settings(
        paperless={
            "url": "http://paperless.example",
            "api_token": "token",
        },
        processing={
            "backfill_comparison_version": "2026-07",
        },
    )

    assert settings.processing.backfill_comparison_version == "2026-07"


def test_processing_delay_between_documents_seconds_defaults_to_disabled():
    settings = Settings(
        paperless={
            "url": "http://paperless.example",
            "api_token": "token",
        },
    )

    assert settings.processing.delay_between_documents_seconds == 0


def test_load_settings_reads_non_secret_values_from_yaml(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
paperless:
  url: http://paperless.example/
codex:
  command: /usr/local/bin/codex
  model: gpt-5.1
  timeout: 30
  max_content_chars: 1234
  reasoning_effort: low
attachments:
  enabled: false
  max_bytes: 42
  supported_mime_types:
    - application/pdf
    - image/png
metadata_guidance:
  tags:
    Tax Deduction:
      use_when: Actual deductible expenses
      avoid_when: Routine Tax Invoice bills
      protected: true
    Legacy Bill:
      deprecated: true
  document_types:
    Bill:
      use_when: Payment requested
  storage_paths:
    Nick:
      use_when: Documents addressed to Nick
processing:
  delay_between_documents_seconds: 1.5
  backfill_comparison_version: 2026-07
""",
        encoding="utf-8",
    )

    settings = load_settings(
        config_path=config_path,
        environ={"PAPERLESS_API_TOKEN": "token"},
    )

    assert settings.paperless.url == "http://paperless.example"
    assert settings.paperless.api_token == "token"
    assert settings.codex.command == "/usr/local/bin/codex"
    assert settings.codex.model == "gpt-5.1"
    assert settings.codex.timeout == 30
    assert settings.codex.max_content_chars == 1234
    assert settings.codex.reasoning_effort == "low"
    assert settings.attachments.enabled is False
    assert settings.attachments.max_bytes == 42
    assert settings.attachments.supported_mime_types == ["application/pdf", "image/png"]
    assert settings.metadata_guidance.tags["tax deduction"].entry.use_when == (
        "Actual deductible expenses"
    )
    assert settings.metadata_guidance.tags["tax deduction"].entry.protected is True
    assert settings.metadata_guidance.tags["legacy bill"].entry.deprecated is True
    assert settings.metadata_guidance.document_types["bill"].entry.use_when == "Payment requested"
    assert settings.metadata_guidance.storage_paths["nick"].entry.use_when == (
        "Documents addressed to Nick"
    )
    assert settings.processing.delay_between_documents_seconds == 1.5
    assert settings.processing.backfill_comparison_version == "2026-07"


def test_load_settings_keeps_paperless_token_in_environment(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
paperless:
  url: http://paperless.example
  token: should-not-be-here
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        load_settings(
            config_path=config_path,
            environ={"PAPERLESS_API_TOKEN": "token"},
        )


def test_load_settings_requires_config_file(tmp_path: Path):
    with pytest.raises(SystemExit):
        load_settings(
            config_path=tmp_path / "missing.yaml",
            environ={"PAPERLESS_API_TOKEN": "token"},
        )
