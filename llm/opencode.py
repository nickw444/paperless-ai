"""Opencode CLI agent implementation."""

from __future__ import annotations

from config.settings import settings
from llm.base import CommandLineAgent


class OpencodeClient(CommandLineAgent):
    """Client wrapper around the Opencode CLI."""

    def __init__(self):
        super().__init__(
            timeout=settings.opencode_timeout or settings.claude_timeout,
            max_content_chars=(
                settings.opencode_max_content_chars or settings.claude_max_content_chars
            ),
        )
        self.command = settings.opencode_command
        self.model = settings.opencode_model

    def _generate_session_id(self) -> str | None:
        """Opencode does not currently support session IDs for non-interactive runs."""
        return None

    def _build_prompt(
        self,
        *,
        content: str,
        temp_path: str,  # noqa: ARG002 - Opencode prompt embeds content directly
        available_types,
        available_tags,
        available_correspondents,
        available_storage_paths,
    ) -> str:
        """Build the categorization prompt embedding the OCR content."""
        content_reference = (
            "The OCR content is provided below between <ocr_content> tags. "
            "Use ONLY that text for analysis.\n"
            f"<ocr_content>\n{content}\n</ocr_content>"
        )
        return self._build_categorization_prompt(
            content_reference=content_reference,
            available_types=available_types,
            available_tags=available_tags,
            available_correspondents=available_correspondents,
            available_storage_paths=available_storage_paths,
        )

    def _build_subprocess_args(
        self,
        *,
        prompt: str,
        temp_path: str,
        session_id: str | None,  # noqa: ARG002 - maintained for signature compatibility
        content: str,  # noqa: ARG002 - Opencode receives content in the prompt
    ):
        """Construct subprocess arguments for the Opencode CLI."""
        command = [self.command, "--model", self.model, "run"]

        # Read prompt from stdin to avoid shell length limits
        command.append("-")

        return command, {"input": prompt}
