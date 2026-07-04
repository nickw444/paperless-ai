"""Configuration management for Paperless-AI."""

import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    paperless_url: str = Field(..., description="URL of the Paperless-ngx instance")
    paperless_api_token: str = Field(..., description="API token for Paperless-ngx")
    codex_command: str = Field(default="codex", description="Path to Codex CLI")
    codex_model: str | None = Field(default="gpt-5", description="Codex model to use")
    codex_timeout: int = Field(default=120, description="Timeout for Codex responses in seconds")
    codex_max_content_chars: int = Field(
        default=2000,
        description="Maximum characters of document content to send to Codex",
    )
    codex_reasoning_effort: str | None = Field(
        default="minimal",
        description='Codex reasoning effort passed via "--config model_reasoning_effort=<value>"',
    )
    enable_document_attachments: bool = Field(
        default=True,
        description="Download supported Paperless document files for agent context",
    )
    max_attachment_bytes: int = Field(
        default=20_000_000,
        description="Maximum downloaded document attachment size in bytes",
    )
    supported_attachment_mime_types: str = Field(
        default="application/pdf,image/jpeg,image/png",
        description="MIME types that can be supplied as document attachments",
    )
    protected_tags: str = Field(
        default="Inbox",
        description="Comma-separated tag names that should never be removed from documents",
    )
    metadata_guidance_file: str | None = Field(
        default="metadata_guidance.yaml",
        description=(
            "Path to YAML file with allowed tags, document types, and storage paths "
            "plus usage guidance"
        ),
    )
    processing_delay_between_documents_seconds: float = Field(
        default=0,
        ge=0,
        description="Delay between document analyses in seconds (0 disables delay)",
    )
    paperless_ai_processing_version: str = Field(
        default="1",
        description="User-defined paperless-ai processing version for backfill detection",
    )
    paperless_ai_version_field_name: str = Field(
        default="paperless-ai-version",
        description="Paperless custom field name for the paperless-ai processing version",
    )
    paperless_ai_model_field_name: str = Field(
        default="paperless-ai-model",
        description="Paperless custom field name for the model used by paperless-ai",
    )
    paperless_ai_tokens_field_name: str = Field(
        default="paperless-ai-tokens",
        description="Paperless custom field name for token metadata written as JSON",
    )

    @field_validator("paperless_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL doesn't end with a trailing slash."""
        return v.rstrip("/")

    @property
    def parsed_supported_attachment_mime_types(self) -> list[str]:
        """Return supported attachment MIME types as a normalized list."""
        return [
            item.strip().lower()
            for item in self.supported_attachment_mime_types.split(",")
            if item.strip()
        ]

    @property
    def parsed_protected_tags(self) -> list[str]:
        """Return protected tag names as a normalized list."""
        return [item.strip() for item in self.protected_tags.split(",") if item.strip()]


def load_settings() -> Settings:
    """Load settings from .env file and environment variables."""
    # Look for .env file in project root
    env_path = Path.cwd() / ".env"

    if env_path.exists():
        load_dotenv(env_path)
    else:
        print("Warning: .env file not found. Using environment variables only.", file=sys.stderr)

    try:
        return Settings()
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        print("\nRequired environment variables:", file=sys.stderr)
        print("  - PAPERLESS_URL: URL of your Paperless-ngx instance", file=sys.stderr)
        print("  - PAPERLESS_API_TOKEN: API token from Paperless", file=sys.stderr)
        print("\nOptional environment variables:", file=sys.stderr)
        print("  - CODEX_COMMAND: Path to Codex CLI (default: codex)", file=sys.stderr)
        print("  - CODEX_MODEL: Codex model to use (default: gpt-5)", file=sys.stderr)
        print("  - CODEX_TIMEOUT: Timeout in seconds (default: 120)", file=sys.stderr)
        print(
            "  - CODEX_MAX_CONTENT_CHARS: Max document chars to analyze (default: 2000)",
            file=sys.stderr,
        )
        print(
            '  - CODEX_REASONING_EFFORT: Reasoning effort (default: "minimal")',
            file=sys.stderr,
        )
        print(
            "  - ENABLE_DOCUMENT_ATTACHMENTS: Download supported files for context (default: true)",
            file=sys.stderr,
        )
        print(
            "  - MAX_ATTACHMENT_BYTES: Max attachment size in bytes (default: 20000000)",
            file=sys.stderr,
        )
        print(
            "  - SUPPORTED_ATTACHMENT_MIME_TYPES: Comma-separated MIME types "
            "(default: application/pdf,image/jpeg,image/png)",
            file=sys.stderr,
        )
        print(
            '  - PROTECTED_TAGS: Comma-separated tag names to never remove (default: "Inbox")',
            file=sys.stderr,
        )
        print(
            "  - METADATA_GUIDANCE_FILE: Path to YAML metadata guidance "
            "(default: metadata_guidance.yaml)",
            file=sys.stderr,
        )
        print(
            "  - PROCESSING_DELAY_BETWEEN_DOCUMENTS_SECONDS: Delay between document analyses "
            "(default: 0, disabled)",
            file=sys.stderr,
        )
        print(
            '  - PAPERLESS_AI_PROCESSING_VERSION: User-defined processing version (default: "1")',
            file=sys.stderr,
        )
        print(
            "  - PAPERLESS_AI_VERSION_FIELD_NAME: Custom field name "
            '(default: "paperless-ai-version")',
            file=sys.stderr,
        )
        print(
            '  - PAPERLESS_AI_MODEL_FIELD_NAME: Custom field name (default: "paperless-ai-model")',
            file=sys.stderr,
        )
        print(
            "  - PAPERLESS_AI_TOKENS_FIELD_NAME: Custom field name "
            '(default: "paperless-ai-tokens")',
            file=sys.stderr,
        )
        sys.exit(1)


# Global settings instance
settings = load_settings()
