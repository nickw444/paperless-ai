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
    tags: list[str] | None = None
    correspondent: str | None = None
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
    ) -> ClaudeResponse:
        """
        Categorize a document using Claude.

        Args:
            ocr_content: The OCR text content of the document
            available_types: List of available document type names
            available_tags: List of available tag names
            available_correspondents: List of available correspondent names

        Returns:
            ClaudeResponse with parsed categorization suggestions
        """
        # Build the prompt
        prompt = self._build_prompt(available_types, available_tags, available_correspondents)

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
    ) -> str:
        """Build the categorization prompt."""
        types_str = ", ".join(available_types) if available_types else "None available"
        tags_str = ", ".join(available_tags) if available_tags else "None available"
        correspondents_str = (
            ", ".join(available_correspondents) if available_correspondents else "None available"
        )

        return f"""You are helping categorize a document in Paperless-ngx.

The OCR content of the document is in the file: @{{TEMP_FILE}}

Based on this content, suggest:
1. An appropriate title (concise, descriptive)
2. Document type from the available options
3. Relevant tags from the available options
4. Correspondent if identifiable

Available document types: {types_str}
Available tags: {tags_str}
Available correspondents: {correspondents_str}

Respond in the following format:
TITLE: <suggested title>
TYPE: <document type or "None">
TAGS: <comma-separated tags or "None">
CORRESPONDENT: <correspondent name or "None">"""

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
                parsed.document_type = doc_type if doc_type.lower() != "none" else None

            elif line.startswith("TAGS:"):
                tags_str = line[5:].strip()
                if tags_str.lower() != "none":
                    # Split by comma and clean up whitespace
                    parsed.tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
                else:
                    parsed.tags = None

            elif line.startswith("CORRESPONDENT:"):
                correspondent = line[14:].strip()
                parsed.correspondent = correspondent if correspondent.lower() != "none" else None

        return parsed
