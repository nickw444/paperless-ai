"""Tests for application settings parsing."""

from config.settings import Settings


def test_supported_attachment_mime_types_parse_from_comma_separated_string():
    settings = Settings(
        paperless_url="http://paperless.example",
        paperless_api_token="token",
        supported_attachment_mime_types="application/pdf, image/png",
    )

    assert settings.parsed_supported_attachment_mime_types == ["application/pdf", "image/png"]
