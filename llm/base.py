"""Base types and helpers for command-line LLM agents."""

from __future__ import annotations

import subprocess
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AgentResponse:
    """Structured categorization response from an AI agent."""

    title: str | None = None
    document_type: str | None = None
    document_type_is_new: bool = False
    tags: list[str] | None = None
    tags_existing: list[str] | None = None
    tags_new: list[str] | None = None
    correspondent: str | None = None
    correspondent_is_new: bool = False
    storage_path: str | None = None
    storage_path_is_new: bool = False
    raw_response: str = ""
    error: str | None = None


class CommandLineAgent(ABC):
    """Reusable workflow for running categorization via CLI-based LLM agents."""

    def __init__(self, *, timeout: int, max_content_chars: int, max_retries: int = 3):
        self.timeout = timeout
        self.max_content_chars = max_content_chars
        self.max_retries = max_retries

    def categorize_document(
        self,
        ocr_content: str,
        available_types: Sequence[str],
        available_tags: Sequence[str],
        available_correspondents: Sequence[str],
        available_storage_paths: Sequence[str],
    ) -> AgentResponse:
        """Execute the agent to categorize a document."""
        prepared_content = self._prepare_content(ocr_content)

        for attempt in range(self.max_retries):
            temp_file_path: str | None = None
            try:
                temp_file_path = self._write_temp_file(prepared_content)
                prompt = self._build_prompt(
                    content=prepared_content,
                    temp_path=temp_file_path,
                    available_types=available_types,
                    available_tags=available_tags,
                    available_correspondents=available_correspondents,
                    available_storage_paths=available_storage_paths,
                )
                session_id = self._generate_session_id()
                command, extra_kwargs = self._build_subprocess_args(
                    prompt=prompt,
                    temp_path=temp_file_path,
                    session_id=session_id,
                    content=prepared_content,
                )
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=True,
                    **extra_kwargs,
                )
                return self._parse_response(result.stdout)
            except subprocess.TimeoutExpired:
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)
                    continue
                return AgentResponse(error="Agent request timed out after multiple retries")
            except subprocess.CalledProcessError as exc:
                return AgentResponse(error=self._format_process_error(exc))
            except Exception as exc:  # noqa: BLE001 - bubble unexpected issues to callers
                return AgentResponse(error=f"Unexpected error: {exc}")
            finally:
                if temp_file_path:
                    Path(temp_file_path).unlink(missing_ok=True)

        return AgentResponse(error="Failed to get response from agent")

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
        ) as temp_file:
            temp_file.write(content)
            return temp_file.name

    def _generate_session_id(self) -> str | None:
        """Generate a session identifier when the agent supports one."""
        return str(uuid.uuid4())

    @staticmethod
    def _format_option_list(options: Sequence[str]) -> str:
        """Return a human-readable list of options."""
        return ", ".join(options) if options else "None available"

    @staticmethod
    def _format_process_error(error: subprocess.CalledProcessError) -> str:
        """Return a helpful error message for subprocess failures."""
        message = f"Agent CLI failed with exit code {error.returncode}"
        if error.stderr:
            message += f"\nStderr: {error.stderr.strip()}"
        if error.stdout:
            message += f"\nStdout: {error.stdout.strip()}"
        return message

    def _parse_response(self, response: str) -> AgentResponse:
        """Parse the structured response returned by the agent."""
        lines = response.strip().split("\n")
        parsed = AgentResponse(raw_response=response)

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("TITLE:"):
                title = stripped[6:].strip()
                parsed.title = title if title.lower() != "none" else None

            elif stripped.startswith("TYPE:"):
                doc_type = stripped[5:].strip()
                if doc_type.lower() != "none":
                    if doc_type.startswith("NEW:"):
                        parsed.document_type = doc_type[4:].strip()
                        parsed.document_type_is_new = True
                    else:
                        parsed.document_type = doc_type
                        parsed.document_type_is_new = False
                else:
                    parsed.document_type = None
                    parsed.document_type_is_new = False

            elif stripped.startswith("TAGS:"):
                tags_str = stripped[5:].strip()
                if tags_str.lower() != "none":
                    all_tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
                    existing_tags: list[str] = []
                    new_tags: list[str] = []

                    for tag in all_tags:
                        if tag.startswith("NEW:"):
                            new_tags.append(tag[4:].strip())
                        else:
                            existing_tags.append(tag)

                    parsed.tags = existing_tags + new_tags if all_tags else None
                    parsed.tags_existing = existing_tags or None
                    parsed.tags_new = new_tags or None
                else:
                    parsed.tags = None
                    parsed.tags_existing = None
                    parsed.tags_new = None

            elif stripped.startswith("CORRESPONDENT:"):
                correspondent = stripped[14:].strip()
                if correspondent.lower() != "none":
                    if correspondent.startswith("NEW:"):
                        parsed.correspondent = correspondent[4:].strip()
                        parsed.correspondent_is_new = True
                    else:
                        parsed.correspondent = correspondent
                        parsed.correspondent_is_new = False
                else:
                    parsed.correspondent = None
                    parsed.correspondent_is_new = False

            elif stripped.startswith("STORAGE_PATH:"):
                storage_path = stripped[13:].strip()
                if storage_path.lower() != "none":
                    if storage_path.startswith("NEW:"):
                        parsed.storage_path = storage_path[4:].strip()
                        parsed.storage_path_is_new = True
                    else:
                        parsed.storage_path = storage_path
                        parsed.storage_path_is_new = False
                else:
                    parsed.storage_path = None
                    parsed.storage_path_is_new = False

        return parsed

    @abstractmethod
    def _build_prompt(
        self,
        *,
        content: str,
        temp_path: str,
        available_types: Sequence[str],
        available_tags: Sequence[str],
        available_correspondents: Sequence[str],
        available_storage_paths: Sequence[str],
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
    ) -> tuple[list[str], dict[str, Any]]:
        """Return command arguments and keyword overrides for subprocess.run."""
