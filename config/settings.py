"""Configuration management for Paperless-AI."""

import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    paperless_url: str = Field(..., description="URL of the Paperless-ngx instance")
    paperless_api_token: str = Field(..., description="API token for Paperless-ngx")
    ai_agent: str = Field(
        default="claude",
        validation_alias="AI_AGENT",
        description="LLM agent backend to use (claude or codex)",
    )
    claude_command: str = Field(default="claude", description="Path to Claude CLI")
    claude_timeout: int = Field(default=120, description="Timeout for Claude responses in seconds")
    claude_max_content_chars: int = Field(
        default=2000, description="Maximum characters of document content to send to Claude"
    )
    claude_model: str | None = Field(default="sonnet", description="Claude model to use")
    codex_command: str = Field(default="codex", description="Path to Codex CLI")
    codex_model: str | None = Field(
        default="gpt-5", description="Codex model to use"
    )
    codex_timeout: int | None = Field(
        default=120, description="Timeout override for Codex responses in seconds"
    )
    codex_max_content_chars: int | None = Field(
        default=None,
        description=(
            "Maximum characters of document content to send to Codex "
            "(defaults to the Claude limit)"
        ),
    )
    codex_reasoning_effort: str | None = Field(
        default="minimal",
        description='Codex reasoning effort passed via "--config model_reasoning_effort=<value>"',
    )

    @field_validator("paperless_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL doesn't end with a trailing slash."""
        return v.rstrip("/")

    @field_validator("ai_agent")
    @classmethod
    def validate_agent(cls, value: str) -> str:
        """Ensure the requested agent backend is supported."""
        normalized = value.lower()
        if normalized not in {"claude", "codex"}:
            raise ValueError("AI_AGENT must be either 'claude' or 'codex'")
        return normalized

    class Config:
        env_file = ".env"
        case_sensitive = False


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
        print(
            "  - AI_AGENT: Active agent backend (claude or codex; default: claude)",
            file=sys.stderr,
        )
        print("  - CLAUDE_COMMAND: Path to Claude CLI (default: claude)", file=sys.stderr)
        print("  - CLAUDE_MODEL: Claude model to use (default: sonnet)", file=sys.stderr)
        print("  - CLAUDE_TIMEOUT: Timeout in seconds (default: 30)", file=sys.stderr)
        print(
            "  - CLAUDE_MAX_CONTENT_CHARS: Max document chars to analyze (default: 2000)",
            file=sys.stderr,
        )
        print("  - CODEX_COMMAND: Path to Codex CLI (default: codex)", file=sys.stderr)
        print("  - CODEX_MODEL: Codex model to use (default: gpt-5)", file=sys.stderr)
        print("  - CODEX_TIMEOUT: Timeout in seconds (default: CLAUDE_TIMEOUT)", file=sys.stderr)
        print(
            "  - CODEX_MAX_CONTENT_CHARS: Max document chars to analyze (default: CLAUDE limit)",
            file=sys.stderr,
        )
        print(
            '  - CODEX_REASONING_EFFORT: Reasoning effort (default: "minimal")',
            file=sys.stderr,
        )
        sys.exit(1)


# Global settings instance
settings = load_settings()
