"""Claude CLI agent implementation."""

from __future__ import annotations

import json
from typing import Any

from config.settings import settings
from llm.base import CommandLineAgent
from llm.parsing import extract_claude_structured_output
from llm.prompts import build_categorization_prompt_with_files
from llm.schemas import AvailableOptions, CurrentMetadata


class ClaudeClient(CommandLineAgent):
    """Client wrapper around the Claude Code CLI."""

    def __init__(self, *, debug: bool = False):
        super().__init__(
            timeout=settings.claude_timeout,
            max_content_chars=settings.claude_max_content_chars,
            debug=debug,
        )
        self.command = settings.claude_command
        self.model = settings.claude_model

    def _extract_structured_payload(self, stdout: str, output_path: str | None) -> dict[str, Any]:
        """Extract structured_output from Claude JSON stdout."""
        del output_path
        return extract_claude_structured_output(stdout)

    def _build_prompt(
        self,
        *,
        content: str,
        temp_path: str,
        options_path: str,
        available_options: AvailableOptions,
        current_metadata: CurrentMetadata,
    ) -> str:
        """Build the categorization prompt referencing the temp files."""
        del content, available_options
        return build_categorization_prompt_with_files(
            ocr_path=temp_path,
            options_path=options_path,
            current_metadata=current_metadata,
        )

    def _build_subprocess_args(
        self,
        *,
        prompt: str,
        temp_path: str,
        session_id: str | None,
        content: str,
        json_schema: dict[str, Any],
        schema_path: str,
    ):
        """Construct subprocess arguments for the Claude CLI."""
        del temp_path, content, schema_path
        command = [self.command]

        if self.model:
            command += ["--model", self.model]

        command += [
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(json_schema),
            "-p",
            prompt,
        ]

        if session_id:
            command += ["--session-id", session_id]

        return command, {}, None
