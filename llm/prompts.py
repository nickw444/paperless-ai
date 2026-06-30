"""Shared prompt templates for document categorization agents."""

import json

from llm.schemas import AvailableOptions


def build_categorization_instructions() -> str:
    """Return shared categorization instructions (output format is enforced by JSON schema)."""
    return """Return IDs from available_options in your response.
Never return entity names for existing items.

Based on the document content and available_options:
1. Suggest an appropriate title (concise, descriptive)
2. Set document_type_id to the best matching id from available_options.document_types, or null
3. Set tag_ids to relevant ids from available_options.tags (empty list if none apply)
4. Set correspondent_id to a matching id from available_options.correspondents, OR set
   new_correspondent_name when no listed correspondent fits (not both)

CORRESPONDENT MATCHING:
- Scan available_options.correspondents for exact matches first (case-insensitive)
- Then look for close matches ("Amazon.com" → "Amazon", "Dr. Smith's Office" → "Dr. Smith")
- Only use new_correspondent_name when no correspondent in the list fits
- Normalize new names: drop legal suffixes (Inc., LLC), URLs, and excess punctuation

5. Set storage_path_id to the best matching id from available_options.storage_paths, or null

SEMANTIC TAG MATCHING:
- Tags should reflect what the document IS ABOUT, not keywords that merely appear in it
- Utility bill for 123 Main St → tag that property; payslip mentioning an address → do not
- Ask: "Is this document primarily ABOUT [tag concept]?" If no, do not include the tag

DOCUMENT TYPE AND STORAGE PATH:
- Pick the single best match by id, or null if nothing fits"""


def build_categorization_preamble() -> str:
    """Return role, input overview, and task instructions before document data."""
    instructions = build_categorization_instructions()
    return f"""You are helping categorize a document in Paperless-ngx.

Below you will receive:
- ocr_content: OCR text of the document. Use ONLY this text for analysis.
- available_options: JSON listing valid Paperless entities as {{"id": <int>, "name": "<str>"}}.

{instructions}"""


def format_available_options_json(available_options: AvailableOptions) -> str:
    """Serialize available options as compact JSON for embedding in prompts."""
    return json.dumps(available_options.model_dump(), separators=(",", ":"))


def build_embedded_categorization_data(
    *,
    content: str,
    available_options: AvailableOptions,
) -> str:
    """Return tagged OCR and options blocks for inline prompt embedding."""
    options_json = format_available_options_json(available_options)
    return f"""<ocr_content>
{content}
</ocr_content>

<available_options>
{options_json}
</available_options>"""


def build_categorization_prompt(
    *,
    content: str,
    available_options: AvailableOptions,
) -> str:
    """Build a full categorization prompt with instructions first, then inline data."""
    return f"""{build_categorization_preamble()}

{build_embedded_categorization_data(content=content, available_options=available_options)}"""


def build_categorization_prompt_with_files(
    *,
    ocr_path: str,
    options_path: str,
) -> str:
    """Build a categorization prompt with file references after the instructions."""
    return f"""{build_categorization_preamble()}

The OCR content is in: @{ocr_path}
The available Paperless metadata options are in: @{options_path}"""


def materialize_prompt_for_debug(
    prompt: str,
    *,
    content: str,
    available_options: AvailableOptions,
) -> str | None:
    """Inline file-backed prompt contents for debug display."""
    if ": @" not in prompt:
        return None
    return build_categorization_prompt(content=content, available_options=available_options)
