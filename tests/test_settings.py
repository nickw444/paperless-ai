"""Tests for application settings parsing."""

from config.settings import Settings


def test_supported_attachment_mime_types_parse_from_comma_separated_string():
    settings = Settings(
        paperless_url="http://paperless.example",
        paperless_api_token="token",
        supported_attachment_mime_types="application/pdf, image/png",
    )

    assert settings.parsed_supported_attachment_mime_types == ["application/pdf", "image/png"]


def test_protected_tags_parse_from_comma_separated_string():
    settings = Settings(
        paperless_url="http://paperless.example",
        paperless_api_token="token",
        protected_tags="Inbox, From Email, Tax Deduction",
    )

    assert settings.parsed_protected_tags == ["Inbox", "From Email", "Tax Deduction"]


def test_processing_metadata_settings_have_hyphenated_defaults():
    assert Settings.model_fields["paperless_ai_processing_version"].default == "1"
    assert (
        Settings.model_fields["paperless_ai_version_field_name"].default == "paperless-ai-version"
    )
    assert Settings.model_fields["paperless_ai_model_field_name"].default == "paperless-ai-model"
    assert Settings.model_fields["paperless_ai_tokens_field_name"].default == "paperless-ai-tokens"


def test_processing_metadata_field_names_can_be_overridden():
    settings = Settings(
        paperless_url="http://paperless.example",
        paperless_api_token="token",
        paperless_ai_processing_version="2026-07",
        paperless_ai_version_field_name="ai-version",
        paperless_ai_model_field_name="ai-model",
        paperless_ai_tokens_field_name="ai-tokens",
    )

    assert settings.paperless_ai_processing_version == "2026-07"
    assert settings.paperless_ai_version_field_name == "ai-version"
    assert settings.paperless_ai_model_field_name == "ai-model"
    assert settings.paperless_ai_tokens_field_name == "ai-tokens"


def test_processing_delay_between_documents_seconds_defaults_to_disabled():
    assert Settings.model_fields["processing_delay_between_documents_seconds"].default == 0
