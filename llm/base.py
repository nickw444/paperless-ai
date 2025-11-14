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

    def _build_categorization_prompt(
        self,
        *,
        content_reference: str,
        available_types: Sequence[str],
        available_tags: Sequence[str],
        available_correspondents: Sequence[str],
        available_storage_paths: Sequence[str],
    ) -> str:
        """Build the common categorization prompt with the provided content reference."""
        types_str = self._format_option_list(available_types)
        tags_str = self._format_option_list(available_tags)
        correspondents_str = self._format_option_list(available_correspondents)
        storage_paths_str = self._format_option_list(available_storage_paths)

        return f"""You are helping categorize a document in Paperless-ngx.

{content_reference}

Available document types: {types_str}
Available tags: {tags_str}
Available correspondents: {correspondents_str}
Available storage paths: {storage_paths_str}

Based on the content:
1. Suggest an appropriate title (concise, descriptive)
2. Choose a document type from available options (select the best match or "None")
3. Choose relevant tags from available options (select all that apply or "None")
4. Choose a correspondent from available options, OR if none match suggest "NEW: <name>"
5. Choose a storage path from available options (select the best match or "None")

IMPORTANT:
- Only suggest NEW correspondents when confident they should exist but aren't in the list
- Do NOT suggest NEW tags, document types, or storage paths - only use existing options

MATCHING GUIDELINES FOR CORRESPONDENTS - FOLLOW THIS PROCESS:

Step 1: CHECK FOR EXACT MATCHES FIRST (case-insensitive)
- Before suggesting a NEW correspondent, carefully scan the ENTIRE available list
- Look for exact matches ignoring case (e.g., "Amber Electric" matches "AMBER ELECTRIC")
- If you find an exact match, USE IT - never suggest NEW for exact matches

Step 2: CHECK FOR CLOSE MATCHES
- If no exact match, look for very similar names:
  - "Amazon.com" should match "Amazon"
  - "Dr. Smith's Office" should match "Dr. Smith"
  - "City Bank" should match "City Bank Australia"
- When in doubt, prefer matching an existing correspondent over creating new

Step 3: ONLY THEN suggest NEW
- Only suggest NEW correspondents when you've carefully checked and found no reasonable match
- Examples when NEW is appropriate:
  - Document from "Netflix", only "Amazon" and "Utilities" exist → suggest "NEW: Netflix"
  - Document from "Target", list has "Walmart, Costco, IKEA" → suggest "NEW: Target"

NORMALIZATION FOR NEW CORRESPONDENTS:
- When suggesting NEW correspondents, use clean, canonical names:
  - "Amazon.com, Inc." → "NEW: Amazon"
  - "Dr. John Smith, MD" → "NEW: Dr. John Smith"
  - "PG&E - Pacific Gas & Electric" → "NEW: Pacific Gas & Electric"
- Avoid URLs, legal suffixes (Inc., LLC), or extra punctuation unless essential

SEMANTIC TAG MATCHING - CRITICAL:
- Tags should reflect what the document IS ABOUT, not just keywords that appear in it
- Think about the document's PURPOSE and SUBJECT MATTER
- Examples of CORRECT tagging:
  - Utility bill for 123 Main St → tag "123 Main St" (document is ABOUT that property)
  - Payslip mentioning 123 Main St as home address → DON'T tag "123 Main St" (not about property)
  - Travel insurance with 123 Main St → DON'T tag "123 Main St" (not about property)
  - Strata notice for Unit 5 → tag for that address (document is ABOUT property management)
  - Vet invoice for dog "Max" → tag "Max" (document is ABOUT that pet)
  - Resume mentioning "Max" as a name → DON'T tag "Max" (not about that pet)
  - Receipt for charitable donation → tag "Tax Deduction" (document is about a deductible expense)
  - Home office expense receipt → tag "Tax Deduction" (document is about a deductible expense)
  - Bill, invoice or receipt labeled "Tax Invoice" → DON'T tag "Tax" or "Tax Deduction" unless it satisfied the previous rules
- Ask yourself: "Is this document primarily ABOUT [tag concept]?" If no, don't use the tag
- Only select tags that describe the document's core subject matter
- For "Tax" and "Tax Deduction" tags: Only apply to documents that represent actual deductible expenses (donations, home office, income-producing costs, etc.) - NOT to documents that merely mention tax or are labeled as tax invoices

MATCHING FOR DOCUMENT TYPES AND STORAGE PATHS:
- For document type: select the single best match (or "None" if nothing fits)
- For storage path: select the best match (or "None" if unsure)

Respond in this format:
TITLE: <suggested title>
TYPE: <existing type or "None">
TAGS: <comma-separated existing tags or "None">
CORRESPONDENT: <existing correspondent or "NEW: name" or "None">
STORAGE_PATH: <existing storage path or "None">"""

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
