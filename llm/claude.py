"""Claude CLI agent implementation."""

from __future__ import annotations

from config.settings import settings
from llm.base import CommandLineAgent


class ClaudeClient(CommandLineAgent):
    """Client wrapper around the Claude Code CLI."""

    def __init__(self):
        super().__init__(
            timeout=settings.claude_timeout,
            max_content_chars=settings.claude_max_content_chars,
        )
        self.command = settings.claude_command
        self.model = settings.claude_model

    def _build_prompt(
        self,
        *,
        content: str,
        temp_path: str,
        available_types,
        available_tags,
        available_correspondents,
        available_storage_paths,
    ) -> str:
        """Build the categorization prompt referencing the temp file."""
        content_reference = f"The OCR content of the document is in the file: @{temp_path}"
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
        session_id: str | None,
        content: str,
    ):
        """Construct subprocess arguments for the Claude CLI."""
        command = [self.command]

        if self.model:
            command += ["--model", self.model]

        command += ["-p", prompt]

        if session_id:
            command += ["--session-id", session_id]

        return command, {}
