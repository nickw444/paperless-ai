"""Codex CLI agent implementation."""

from __future__ import annotations

from typing import Any

from config.settings import settings
from llm.base import CommandLineAgent
from llm.parsing import extract_codex_structured_output
from llm.prompts import build_categorization_prompt
from llm.schemas import AvailableOptions


class CodexClient(CommandLineAgent):
    """Client wrapper around the Codex CLI."""

    def __init__(self, *, debug: bool = False):
        super().__init__(
            timeout=settings.codex_timeout or settings.claude_timeout,
            max_content_chars=settings.codex_max_content_chars or settings.claude_max_content_chars,
            debug=debug,
        )
        self.command = settings.codex_command
        self.model = settings.codex_model
        self.reasoning_effort = settings.codex_reasoning_effort

    def _generate_session_id(self) -> str | None:
        """Codex does not currently support session IDs for non-interactive runs."""
        return None

    def _extract_structured_payload(self, stdout: str, output_path: str | None) -> dict[str, Any]:
        """Read validated JSON from the Codex output file."""
        del stdout
        if not output_path:
            raise ValueError("Codex requires an output file path")
        return extract_codex_structured_output(output_path)

    def _build_prompt(
        self,
        *,
        content: str,
        temp_path: str,
        options_path: str,
        available_options: AvailableOptions,
    ) -> str:
        """Build the categorization prompt embedding the OCR content and options."""
        del temp_path, options_path
        return build_categorization_prompt(content=content, available_options=available_options)

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
        """Construct subprocess arguments for the Codex CLI."""
        del temp_path, session_id, content, json_schema
        output_path = self._write_output_temp_file()

        command = [self.command, "exec"]

        model = self.model or "gpt-5"
        command += ["--model", model]

        if self.reasoning_effort:
            command += ["--config", f'model_reasoning_effort="{self.reasoning_effort}"']

        command += ["--output-schema", schema_path, "-o", output_path, "-"]

        return command, {"input": prompt}, output_path
