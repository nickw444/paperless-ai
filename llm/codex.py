"""Codex CLI agent for document categorization."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from config.settings import settings
from llm.prompts import build_categorization_prompt
from llm.schemas import (
    AgentCategorizationResult,
    AgentDebugTrace,
    AttachmentDebugMetadata,
    AvailableOptions,
    CategorizationAgentOutput,
    CurrentMetadata,
    build_categorization_json_schema,
    validate_agent_output,
)
from llm.usage import extract_usage
from paperless.models import DocumentAttachment

OCR_PREVIEW_CHARS = 500
CODEX_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png"})


def _read_structured_output(output_path: str) -> dict[str, Any]:
    """Read validated JSON output written by Codex CLI."""
    content = Path(output_path).read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Codex output file is empty: {output_path}")

    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("Codex output is not a JSON object")
    return data


class CodexAgent:
    """Client wrapper around the Codex CLI."""

    def __init__(self, *, debug: bool = False, max_retries: int = 3):
        self.timeout = settings.codex_timeout
        self.max_content_chars = settings.codex_max_content_chars
        self.max_retries = max_retries
        self.debug = debug
        self.command = settings.codex_command
        self.model = settings.codex_model
        self.reasoning_effort = settings.codex_reasoning_effort

    def categorize_document(
        self,
        ocr_content: str,
        available_options: AvailableOptions,
        current_metadata: CurrentMetadata,
        attachment: DocumentAttachment | None = None,
    ) -> AgentCategorizationResult:
        """Execute Codex to categorize a document."""
        prepared_content = self._prepare_content(ocr_content)
        json_schema = build_categorization_json_schema()

        last_raw_response = ""
        last_error = "Failed to get response from agent"
        debug_traces: list[AgentDebugTrace] = []

        for attempt in range(self.max_retries):
            temp_paths: list[str] = []
            trace = self._new_debug_trace(
                attempt=attempt + 1,
                prepared_content=prepared_content,
                available_options=available_options,
                json_schema=json_schema,
                attachment=attachment,
            )
            try:
                schema_path = self._write_json_temp_file(json_schema)
                temp_paths.append(schema_path)

                output_path = self._write_output_temp_file()
                temp_paths.append(output_path)

                prompt = build_categorization_prompt(
                    content=prepared_content,
                    available_options=available_options,
                    current_metadata=current_metadata,
                    attachment=attachment,
                )
                trace.prompt = prompt

                command, extra_kwargs = self._build_command(
                    prompt=prompt,
                    schema_path=schema_path,
                    output_path=output_path,
                    attachment=attachment,
                )
                trace.command = command

                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=True,
                    **extra_kwargs,
                )
                last_raw_response = result.stdout
                trace.stdout = result.stdout
                trace.stderr = result.stderr or ""
                trace.usage_metadata = extract_usage(trace.stderr, trace.command)
                trace.output_file_content = Path(output_path).read_text(encoding="utf-8")

                payload = _read_structured_output(output_path)
                trace.parsed_payload = payload
                output = validate_agent_output(
                    CategorizationAgentOutput.model_validate(payload),
                    available_options,
                )
                trace.validated_output = output
                if self.debug:
                    debug_traces.append(trace)
                return AgentCategorizationResult(
                    output=output,
                    raw_response=last_raw_response,
                    usage_metadata=trace.usage_metadata,
                    debug_traces=debug_traces,
                )
            except subprocess.TimeoutExpired:
                last_error = "Agent request timed out"
                trace.error = last_error
                if self.debug:
                    debug_traces.append(trace)
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                return AgentCategorizationResult(
                    error="Agent request timed out after multiple retries",
                    raw_response=last_raw_response,
                    debug_traces=debug_traces,
                )
            except subprocess.CalledProcessError as exc:
                trace.error = self._format_process_error(exc)
                trace.stdout = exc.stdout or ""
                trace.stderr = exc.stderr or ""
                trace.usage_metadata = extract_usage(trace.stderr, trace.command)
                if self.debug:
                    debug_traces.append(trace)
                return AgentCategorizationResult(
                    error=trace.error,
                    raw_response=exc.stdout or last_raw_response,
                    debug_traces=debug_traces,
                )
            except (ValidationError, json.JSONDecodeError, ValueError, OSError) as exc:
                last_error = f"Invalid agent JSON response: {exc}"
                trace.error = last_error
                if self.debug:
                    debug_traces.append(trace)
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                return AgentCategorizationResult(
                    error=last_error,
                    raw_response=last_raw_response,
                    debug_traces=debug_traces,
                )
            except Exception as exc:  # noqa: BLE001 - bubble unexpected issues to callers
                trace.error = f"Unexpected error: {exc}"
                if self.debug:
                    debug_traces.append(trace)
                return AgentCategorizationResult(
                    error=trace.error,
                    raw_response=last_raw_response,
                    debug_traces=debug_traces,
                )
            finally:
                for path in temp_paths:
                    Path(path).unlink(missing_ok=True)

        return AgentCategorizationResult(
            error=last_error,
            raw_response=last_raw_response,
            debug_traces=debug_traces,
        )

    def _build_command(
        self,
        *,
        prompt: str,
        schema_path: str,
        output_path: str,
        attachment: DocumentAttachment | None = None,
    ) -> tuple[list[str], dict[str, Any]]:
        """Construct subprocess arguments for the Codex CLI."""
        command = [self.command, "exec", "--model", self.model or "gpt-5"]
        if self.reasoning_effort:
            command += ["--config", f'model_reasoning_effort="{self.reasoning_effort}"']
        if attachment and attachment.mime_type in CODEX_IMAGE_MIME_TYPES:
            command += ["--image", attachment.path]
        command += ["--output-schema", schema_path, "-o", output_path, "-"]
        return command, {"input": prompt}

    def _new_debug_trace(
        self,
        *,
        attempt: int,
        prepared_content: str,
        available_options: AvailableOptions,
        json_schema: dict[str, Any],
        attachment: DocumentAttachment | None,
    ) -> AgentDebugTrace:
        """Create a debug trace with common input fields."""
        return AgentDebugTrace(
            attempt=attempt,
            prompt="",
            prepared_content_chars=len(prepared_content),
            ocr_preview=prepared_content[:OCR_PREVIEW_CHARS],
            attachment=_attachment_debug_metadata(attachment),
            available_options=available_options,
            json_schema=json_schema,
        )

    def _prepare_content(self, ocr_content: str) -> str:
        """Optionally truncate the OCR content to a manageable size."""
        if len(ocr_content) <= self.max_content_chars:
            return ocr_content

        truncated = ocr_content[: self.max_content_chars]
        return f"{truncated}\n\n[Content truncated at {self.max_content_chars} characters]"

    def _write_json_temp_file(self, data: dict[str, Any]) -> str:
        """Persist JSON schema to a temporary file."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            prefix="paperless_schema_",
            encoding="utf-8",
        ) as temp_file:
            json.dump(data, temp_file)
            return temp_file.name

    def _write_output_temp_file(self) -> str:
        """Create an empty temporary file for Codex JSON output."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            prefix="paperless_output_",
            encoding="utf-8",
        ) as temp_file:
            return temp_file.name

    @staticmethod
    def _format_process_error(error: subprocess.CalledProcessError) -> str:
        """Return a helpful error message for subprocess failures."""
        message = f"Agent CLI failed with exit code {error.returncode}"
        if error.stderr:
            message += f"\nStderr: {error.stderr.strip()}"
        if error.stdout:
            message += f"\nStdout: {error.stdout.strip()}"
        return message


def _attachment_debug_metadata(
    attachment: DocumentAttachment | None,
) -> AttachmentDebugMetadata | None:
    if attachment is None:
        return None
    return AttachmentDebugMetadata(
        path=attachment.path,
        source=attachment.source,
        mime_type=attachment.mime_type,
        filename=attachment.filename,
        byte_size=attachment.byte_size,
    )
