"""Claude CLI wrapper for document categorization."""

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from config.settings import settings


@dataclass
class ClaudeResponse:
    """Parsed response from Claude."""

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


class ClaudeClient:
    """Client for interacting with Claude CLI."""

    def __init__(self):
        """Initialize the Claude CLI client."""
        self.claude_command = settings.claude_command
        self.timeout = settings.claude_timeout
        self.max_retries = 3

    def categorize_document(
        self,
        ocr_content: str,
        available_types: list[str],
        available_tags: list[str],
        available_correspondents: list[str],
        available_storage_paths: list[str],
    ) -> ClaudeResponse:
        """
        Categorize a document using Claude.

        Args:
            ocr_content: The OCR text content of the document
            available_types: List of available document type names
            available_tags: List of available tag names
            available_correspondents: List of available correspondent names
            available_storage_paths: List of available storage path names

        Returns:
            ClaudeResponse with parsed categorization suggestions
        """
        # Build the prompt
        prompt = self._build_prompt(
            available_types, available_tags, available_correspondents, available_storage_paths
        )

        # Try with retries
        for attempt in range(self.max_retries):
            try:
                response = self._call_claude(ocr_content, prompt)
                return self._parse_response(response)
            except subprocess.TimeoutExpired:
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)  # Exponential backoff
                    continue
                return ClaudeResponse(error="Claude request timed out after multiple retries")
            except subprocess.CalledProcessError as e:
                return ClaudeResponse(error=f"Claude CLI error: {e.stderr.decode()}")
            except Exception as e:
                return ClaudeResponse(error=f"Unexpected error: {str(e)}")

        return ClaudeResponse(error="Failed to get response from Claude")

    def _build_prompt(
        self,
        available_types: list[str],
        available_tags: list[str],
        available_correspondents: list[str],
        available_storage_paths: list[str],
    ) -> str:
        """Build the categorization prompt."""
        types_str = ", ".join(available_types) if available_types else "None available"
        tags_str = ", ".join(available_tags) if available_tags else "None available"
        correspondents_str = (
            ", ".join(available_correspondents) if available_correspondents else "None available"
        )
        storage_paths_str = (
            ", ".join(available_storage_paths) if available_storage_paths else "None available"
        )

        return f"""You are helping categorize a document in Paperless-ngx.

The OCR content of the document is in the file: @{{TEMP_FILE}}

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

MATCHING GUIDELINES FOR CORRESPONDENTS:
- Try to match existing correspondents even if the name isn't exact. For example:
  - If the document says "Amazon.com" and "Amazon" exists, use "Amazon"
  - If the document says "Dr. Smith's Office" and "Dr. Smith" exists, use "Dr. Smith"
- Only suggest NEW correspondents when there's clearly no reasonable match in the existing list
- Examples:
  - Document from "Amazon", no "Amazon" in list → suggest "NEW: Amazon"
  - Document from "Amazon.com", "Amazon Inc." exists → use "Amazon Inc."
  - Document from "Netflix", only "Amazon" and "Utilities" exist → suggest "NEW: Netflix"

NORMALIZATION FOR NEW CORRESPONDENTS:
- When suggesting NEW correspondents, use clean, canonical names:
  - "Amazon.com" → "NEW: Amazon"
  - "Dr. John Smith, MD" → "NEW: Dr. John Smith"
  - "PG&E - Pacific Gas & Electric" → "NEW: Pacific Gas & Electric"
- Avoid URLs, legal suffixes (Inc., LLC), or extra punctuation unless essential

MATCHING FOR TAGS, TYPES, AND STORAGE PATHS:
- Always select from existing options, choosing the best match
- For tags: select all relevant tags that apply
- For document type: select the single best match (or "None" if nothing fits)
- For storage path: select the best match (or "None" if unsure)

Respond in this format:
TITLE: <suggested title>
TYPE: <existing type or "None">
TAGS: <comma-separated existing tags or "None">
CORRESPONDENT: <existing correspondent or "NEW: name" or "None">
STORAGE_PATH: <existing storage path or "None">"""

    def _call_claude(self, ocr_content: str, prompt_template: str) -> str:
        """Execute Claude CLI with the document content."""
        # Create a temporary file for the OCR content
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="paperless_doc_"
        ) as temp_file:
            temp_file.write(ocr_content)
            temp_path = temp_file.name

        try:
            # Replace placeholder with actual temp file path
            prompt = prompt_template.replace("{TEMP_FILE}", temp_path)

            # Execute Claude CLI
            result = subprocess.run(
                [self.claude_command, "-p", prompt],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=True,
            )

            return result.stdout
        finally:
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)

    def _parse_response(self, response: str) -> ClaudeResponse:
        """Parse Claude's structured response."""
        lines = response.strip().split("\n")
        parsed = ClaudeResponse(raw_response=response)

        for line in lines:
            line = line.strip()

            if line.startswith("TITLE:"):
                title = line[6:].strip()
                parsed.title = title if title.lower() != "none" else None

            elif line.startswith("TYPE:"):
                doc_type = line[5:].strip()
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

            elif line.startswith("TAGS:"):
                tags_str = line[5:].strip()
                if tags_str.lower() != "none":
                    # Split by comma and process each tag
                    all_tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
                    existing_tags = []
                    new_tags = []

                    for tag in all_tags:
                        if tag.startswith("NEW:"):
                            new_tags.append(tag[4:].strip())
                        else:
                            existing_tags.append(tag)

                    # Combine all tags for backward compatibility
                    parsed.tags = existing_tags + new_tags
                    parsed.tags_existing = existing_tags if existing_tags else None
                    parsed.tags_new = new_tags if new_tags else None
                else:
                    parsed.tags = None
                    parsed.tags_existing = None
                    parsed.tags_new = None

            elif line.startswith("CORRESPONDENT:"):
                correspondent = line[14:].strip()
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

            elif line.startswith("STORAGE_PATH:"):
                storage_path = line[13:].strip()
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
