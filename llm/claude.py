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
        types_str = self._format_option_list(available_types)
        tags_str = self._format_option_list(available_tags)
        correspondents_str = self._format_option_list(available_correspondents)
        storage_paths_str = self._format_option_list(available_storage_paths)

        return f"""You are helping categorize a document in Paperless-ngx.

The OCR content of the document is in the file: @{temp_path}

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
- Ask yourself: "Is this document primarily ABOUT [tag concept]?" If no, don't use the tag
- Only select tags that describe the document's core subject matter

MATCHING FOR DOCUMENT TYPES AND STORAGE PATHS:
- For document type: select the single best match (or "None" if nothing fits)
- For storage path: select the best match (or "None" if unsure)

Respond in this format:
TITLE: <suggested title>
TYPE: <existing type or "None">
TAGS: <comma-separated existing tags or "None">
CORRESPONDENT: <existing correspondent or "NEW: name" or "None">
STORAGE_PATH: <existing storage path or "None">"""

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
