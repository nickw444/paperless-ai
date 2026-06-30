"""Base types and helpers for command-line LLM agents."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from llm.prompts import materialize_prompt_for_debug
from llm.schemas import (
    AgentCategorizationResult,
    AgentDebugTrace,
    AvailableOptions,
    CategorizationAgentOutput,
    build_categorization_json_schema,
    validate_agent_output,
)
from llm.usage import extract_agent_usage

OCR_PREVIEW_CHARS = 500


class CommandLineAgent(ABC):
    """Reusable workflow for running categorization via CLI-based LLM agents."""

    def __init__(
        self,
        *,
        timeout: int,
        max_content_chars: int,
        max_retries: int = 3,
        debug: bool = False,
    ):
        self.timeout = timeout
        self.max_content_chars = max_content_chars
        self.max_retries = max_retries
        self.debug = debug

    def categorize_document(
        self,
        ocr_content: str,
        available_options: AvailableOptions,
    ) -> AgentCategorizationResult:
        """Execute the agent to categorize a document."""
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
            )
            try:
                temp_file_path = self._write_temp_file(prepared_content)
                temp_paths.append(temp_file_path)

                options_path = self._write_json_temp_file(
                    available_options.model_dump(),
                    prefix="paperless_options_",
                    compact=True,
                )
                temp_paths.append(options_path)

                schema_path = self._write_json_temp_file(json_schema)
                temp_paths.append(schema_path)

                prompt = self._build_prompt(
                    content=prepared_content,
                    temp_path=temp_file_path,
                    options_path=options_path,
                    available_options=available_options,
                )
                trace.prompt = prompt
                if self.debug:
                    trace.resolved_prompt = materialize_prompt_for_debug(
                        prompt,
                        content=prepared_content,
                        available_options=available_options,
                    )
                session_id = self._generate_session_id()
                command, extra_kwargs, output_path = self._build_subprocess_args(
                    prompt=prompt,
                    temp_path=temp_file_path,
                    session_id=session_id,
                    content=prepared_content,
                    json_schema=json_schema,
                    schema_path=schema_path,
                )
                if output_path:
                    temp_paths.append(output_path)

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
                trace.usage_metadata = extract_agent_usage(
                    stdout=trace.stdout,
                    stderr=trace.stderr,
                    command=trace.command,
                )
                if output_path:
                    trace.output_file_content = Path(output_path).read_text(encoding="utf-8")

                payload = self._extract_structured_payload(result.stdout, output_path)
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
                trace.usage_metadata = extract_agent_usage(
                    stdout=trace.stdout,
                    stderr=trace.stderr,
                    command=trace.command,
                )
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

    def _new_debug_trace(
        self,
        *,
        attempt: int,
        prepared_content: str,
        available_options: AvailableOptions,
        json_schema: dict[str, Any],
    ) -> AgentDebugTrace:
        """Create a debug trace with common input fields."""
        return AgentDebugTrace(
            attempt=attempt,
            prompt="",
            prepared_content_chars=len(prepared_content),
            ocr_preview=prepared_content[:OCR_PREVIEW_CHARS],
            available_options=available_options,
            json_schema=json_schema,
        )

    def _prepare_content(self, ocr_content: str) -> str:
        """Optionally truncate the OCR content to a manageable size."""
        if len(ocr_content) <= self.max_content_chars:
            return ocr_content

        truncated = ocr_content[: self.max_content_chars]
        return f"{truncated}\n\n[Content truncated at {self.max_content_chars} characters]"

    def _write_temp_file(self, content: str) -> str:
        """Persist content to a temporary file for agents that reference files."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            prefix="paperless_doc_",
            encoding="utf-8",
        ) as temp_file:
            temp_file.write(content)
            return temp_file.name

    def _write_json_temp_file(
        self,
        data: dict[str, Any],
        *,
        prefix: str = "paperless_schema_",
        compact: bool = False,
    ) -> str:
        """Persist JSON data to a temporary file."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            prefix=prefix,
            encoding="utf-8",
        ) as temp_file:
            if compact:
                json.dump(data, temp_file, separators=(",", ":"))
            else:
                json.dump(data, temp_file)
            return temp_file.name

    def _write_output_temp_file(self) -> str:
        """Create an empty temporary file for agents that write JSON output."""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            prefix="paperless_output_",
            encoding="utf-8",
        ) as temp_file:
            return temp_file.name

    def _generate_session_id(self) -> str | None:
        """Generate a session identifier when the agent supports one."""
        return str(uuid.uuid4())

    @staticmethod
    def _format_process_error(error: subprocess.CalledProcessError) -> str:
        """Return a helpful error message for subprocess failures."""
        message = f"Agent CLI failed with exit code {error.returncode}"
        if error.stderr:
            message += f"\nStderr: {error.stderr.strip()}"
        if error.stdout:
            message += f"\nStdout: {error.stdout.strip()}"
        return message

    @abstractmethod
    def _extract_structured_payload(self, stdout: str, output_path: str | None) -> dict[str, Any]:
        """Extract the categorization JSON object from provider-specific output."""

    @abstractmethod
    def _build_prompt(
        self,
        *,
        content: str,
        temp_path: str,
        options_path: str,
        available_options: AvailableOptions,
    ) -> str:
        """Create the prompt that will be submitted to the agent."""

    @abstractmethod
    def _build_subprocess_args(
        self,
        *,
        prompt: str,
        temp_path: str,
        session_id: str | None,
        content: str,
        json_schema: dict[str, Any],
        schema_path: str,
    ) -> tuple[list[str], dict[str, Any], str | None]:
        """Return command args, subprocess kwargs, and optional output file path."""
