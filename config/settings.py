"""Configuration management for Paperless-AI."""

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from config.metadata_guidance import MetadataGuidance, load_metadata_guidance_from_mapping

ENV_FILE = ".env"
DEFAULT_CONFIG_FILE = "config.yaml"
CONFIG_FILE_ENV_VAR = "PAPERLESS_AI_CONFIG_FILE"


class PaperlessSettings(BaseModel):
    """Paperless-ngx connection settings."""

    model_config = ConfigDict(extra="ignore")

    url: str = Field(..., description="URL of the Paperless-ngx instance")
    api_token: str = Field(..., description="API token for Paperless-ngx")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL doesn't end with a trailing slash."""
        return v.rstrip("/")


class CodexSettings(BaseModel):
    """Codex CLI settings."""

    model_config = ConfigDict(extra="ignore")

    command: str = Field(default="codex", description="Path to Codex CLI")
    model: str | None = Field(default="gpt-5", description="Codex model to use")
    timeout: int = Field(default=120, description="Timeout for Codex responses in seconds")
    max_content_chars: int = Field(
        default=2000,
        description="Maximum characters of document content to send to Codex",
    )
    reasoning_effort: str | None = Field(
        default="minimal",
        description='Codex reasoning effort passed via "--config model_reasoning_effort=<value>"',
    )


class AttachmentSettings(BaseModel):
    """Document attachment settings."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(
        default=True,
        description="Download supported Paperless document files for agent context",
    )
    max_bytes: int = Field(
        default=20_000_000,
        description="Maximum downloaded document attachment size in bytes",
    )
    supported_mime_types: list[str] = Field(
        default_factory=lambda: ["application/pdf", "image/jpeg", "image/png"],
        description="MIME types that can be supplied as document attachments",
    )

    @field_validator("supported_mime_types")
    @classmethod
    def normalize_supported_mime_types(cls, v: list[str]) -> list[str]:
        """Normalize MIME types loaded from the YAML list."""
        return [item.strip().lower() for item in v if item.strip()]


class ProcessingSettings(BaseModel):
    """Document processing settings."""

    model_config = ConfigDict(extra="ignore")

    delay_between_documents_seconds: float = Field(
        default=0,
        ge=0,
        description="Delay between document analyses in seconds (0 disables delay)",
    )
    backfill_comparison_version: str = Field(
        default="1",
        description=(
            "Marker stored on processed documents and compared by --reprocess-stale "
            "to decide which documents need backfilling"
        ),
    )


class Settings(BaseModel):
    """Application settings loaded from YAML plus environment secrets."""

    model_config = ConfigDict(extra="ignore")

    paperless: PaperlessSettings
    codex: CodexSettings = Field(default_factory=CodexSettings)
    attachments: AttachmentSettings = Field(default_factory=AttachmentSettings)
    protected_tags: list[str] = Field(
        default_factory=lambda: ["Inbox"],
        description="Tag names that should never be removed from documents",
    )
    metadata_guidance: MetadataGuidance = Field(default_factory=MetadataGuidance)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)

    @field_validator("metadata_guidance", mode="before")
    @classmethod
    def parse_metadata_guidance(cls, v: object) -> MetadataGuidance:
        if v is None:
            return MetadataGuidance()
        if isinstance(v, MetadataGuidance):
            return v
        if not isinstance(v, dict):
            raise ValueError("metadata_guidance must be a YAML mapping")
        if not v:
            return MetadataGuidance()
        return load_metadata_guidance_from_mapping(v, path=Path("metadata_guidance"))

    @field_validator("protected_tags")
    @classmethod
    def normalize_protected_tags(cls, v: list[str]) -> list[str]:
        """Normalize protected tag names loaded from the YAML list."""
        return [item.strip() for item in v if item.strip()]


def _load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Configuration file not found: {path}")

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    _reject_yaml_secret(loaded, path=path)
    return loaded


def _reject_yaml_secret(config: Mapping[str, Any], *, path: Path) -> None:
    if "paperless_api_token" in config:
        raise ValueError(
            f"paperless_api_token must not be stored in {path}; use PAPERLESS_API_TOKEN"
        )

    paperless = config.get("paperless")
    if isinstance(paperless, Mapping) and {"api_token", "token", "paperless_api_token"} & set(
        paperless
    ):
        raise ValueError(
            f"Paperless API token must not be stored in {path}; use PAPERLESS_API_TOKEN"
        )


def load_settings(
    *,
    config_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Load settings from YAML configuration and environment secrets."""
    if environ is None:
        env_path = Path.cwd() / ENV_FILE

        if env_path.exists():
            load_dotenv(env_path)
        else:
            print(
                f"Warning: {ENV_FILE} file not found. Reading secrets from process environment.",
                file=sys.stderr,
            )
        environ = os.environ

    if config_path is None:
        config_path = Path(environ.get(CONFIG_FILE_ENV_VAR, DEFAULT_CONFIG_FILE))

    try:
        config = _load_config_file(config_path)
        paperless_config = config.setdefault("paperless", {})
        if not isinstance(paperless_config, dict):
            raise ValueError("paperless must be a YAML mapping")
        paperless_config["api_token"] = environ.get("PAPERLESS_API_TOKEN")
        return Settings(**config)
    except (ValidationError, ValueError) as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        print("\nConfiguration file:", file=sys.stderr)
        print(f"  - {CONFIG_FILE_ENV_VAR}: optional path to YAML config", file=sys.stderr)
        print(f"  - default: {DEFAULT_CONFIG_FILE}", file=sys.stderr)
        print("\nRequired YAML settings:", file=sys.stderr)
        print("  - paperless.url: URL of your Paperless-ngx instance", file=sys.stderr)
        print("\nRequired secret:", file=sys.stderr)
        print("  - PAPERLESS_API_TOKEN: API token from Paperless", file=sys.stderr)
        print("\nOptional YAML settings:", file=sys.stderr)
        print("  - codex.command: Path to Codex CLI (default: codex)", file=sys.stderr)
        print("  - codex.model: Codex model to use (default: gpt-5)", file=sys.stderr)
        print("  - codex.timeout: Timeout in seconds (default: 120)", file=sys.stderr)
        print(
            "  - codex.max_content_chars: Max document chars to analyze (default: 2000)",
            file=sys.stderr,
        )
        print('  - codex.reasoning_effort: Reasoning effort (default: "minimal")', file=sys.stderr)
        print(
            "  - attachments.enabled: Download supported files for context (default: true)",
            file=sys.stderr,
        )
        print(
            "  - attachments.max_bytes: Max attachment size in bytes (default: 20000000)",
            file=sys.stderr,
        )
        print(
            "  - attachments.supported_mime_types: MIME type list "
            "(default: application/pdf, image/jpeg, image/png)",
            file=sys.stderr,
        )
        print('  - protected_tags: tag name list (default: ["Inbox"])', file=sys.stderr)
        print(
            "  - metadata_guidance: tag, document type, and storage path guidance "
            "for agent choices",
            file=sys.stderr,
        )
        print(
            "  - processing.delay_between_documents_seconds: Delay between document analyses "
            "(default: 0, disabled)",
            file=sys.stderr,
        )
        print(
            "  - processing.backfill_comparison_version: marker compared by "
            '--reprocess-stale (default: "1")',
            file=sys.stderr,
        )
        sys.exit(1)


# Global settings instance
settings = load_settings()
