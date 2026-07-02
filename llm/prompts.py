"""Shared prompt templates for document categorization."""

import json

from llm.schemas import AvailableOptions, CurrentMetadata
from paperless.models import DocumentAttachment


def build_categorization_instructions() -> str:
    """Return shared categorization instructions (output format is enforced by JSON schema)."""
    return """Return IDs from available_options in your response.
Never return entity names for existing items.

Based on the document content, current_metadata, and available_options:
1. Suggest an appropriate title (concise, descriptive). Use current_metadata.title as context:
   keep descriptive manual titles; improve generic filenames (e.g. scan.pdf) using OCR content,
   extracted attachment text, or a visual description for photos without clear text.
2. Set content to corrected document OCR text suitable for Paperless-ngx's content field.
   Preserve the document's reading order and meaningful structure such as headings, labels,
   tables, line breaks, checkboxes, and form sections. Correct obvious OCR errors only when
   the intended text is clear from context. Do not summarize, add commentary, invent missing
   values, or omit boilerplate text just because it is repetitive. When ocr_content is empty
   but a document_attachment is provided, extract usable text from the attachment into content.
   If the attachment is a photo or image without clear document text, set content to a concise,
   factual description of what is visible instead of returning null. Include visible subjects,
   setting, notable objects, and any readable text. In this photo case, augment generic titles
   with the main visible subject or scene.
   Return null only when the provided OCR content is already accurate enough or there is not
   enough evidence to improve, extract, or describe it.
3. Set document_date to the document's own date in YYYY-MM-DD format, or null.
   Use dates printed in the document body, letterhead, invoice/receipt dates, statement periods,
   form dates, email headers, or other visible source context. Prefer the date the document was
   issued/sent/created over due dates, payment dates, upload dates, scan dates, or unrelated
   dates mentioned in content. When current_metadata.document_date is already supported by the
   document evidence, return it. Return null only when no reliable document date can be inferred.
4. Set document_type_id to the best matching id from available_options.document_types,
   or null. When current_metadata.document_type is set and still appropriate, return its id;
   change only when OCR or attachment context supports a better match.
5. Set tag_ids to relevant ids from available_options.tags (empty list if none apply).
   Use current_metadata.tags as context; when the same tags still apply, return their ids;
   add or remove only when OCR or attachment context supports the change.
6. Set correspondent_id to a matching id from available_options.correspondents, OR set
   new_correspondent_name when no listed correspondent fits (not both).
   When current_metadata.correspondent is set and still appropriate, return its id.

CORRESPONDENT MATCHING:
- Scan available_options.correspondents for exact matches first (case-insensitive)
- Then look for close matches ("Amazon.com" → "Amazon", "Dr. Smith's Office" → "Dr. Smith")
- Only use new_correspondent_name when no correspondent in the list fits
- Normalize new names: drop legal suffixes (Inc., LLC), URLs, and excess punctuation

7. Set storage_path_id to the best matching id from available_options.storage_paths, or null.
   When current_metadata.storage_path is set and still appropriate, return its id.

SEMANTIC TAG MATCHING:
- Tags should reflect what the document IS ABOUT, not keywords that merely appear in it
- Utility bill for 123 Main St → tag that property; payslip mentioning an address → do not
- Receipt for charitable donation → tag Tax Deduction
- Home office expense receipt → tag Tax Deduction
- Bill, invoice, or receipt labeled "Tax Invoice" → do not tag Tax or Tax Deduction solely
  because of that label
- Ask: "Is this document primarily ABOUT [tag concept]?" If no, do not include the tag

DOCUMENT TYPE AND STORAGE PATH:
- Pick the single best match by id, or null if nothing fits"""


def build_categorization_preamble() -> str:
    """Return role, input overview, and task instructions before document data."""
    instructions = build_categorization_instructions()
    return f"""You are helping categorize a document in Paperless-ngx.

Below you will receive:
- current_metadata: JSON with the document's existing Paperless fields before categorization.
  Entity fields use {{"id": <int>, "name": "<str>"}} (or null when unset).
- ocr_content: OCR text of the document, when available.
- document_attachment: Optional source document file that may provide clearer visual
  context than OCR.
- available_options: JSON listing valid Paperless entities as {{"id": <int>, "name": "<str>"}}.

Use the document attachment and OCR together when both are available. Prefer the attachment for
visual layout, handwriting, forms, logos, and OCR mistakes, but keep OCR as useful text context.

{instructions}"""


def format_available_options_json(available_options: AvailableOptions) -> str:
    """Serialize available options as compact JSON for embedding in prompts."""
    return json.dumps(available_options.model_dump(mode="json"), separators=(",", ":"))


def format_current_metadata_json(current_metadata: CurrentMetadata) -> str:
    """Serialize current metadata as compact JSON for embedding in prompts."""
    return json.dumps(current_metadata.model_dump(mode="json"), separators=(",", ":"))


def build_embedded_categorization_data(
    *,
    content: str,
    available_options: AvailableOptions,
    current_metadata: CurrentMetadata,
) -> str:
    """Return tagged current metadata, OCR, and options blocks for inline prompt embedding."""
    metadata_json = format_current_metadata_json(current_metadata)
    options_json = format_available_options_json(available_options)
    return f"""<current_metadata>
{metadata_json}
</current_metadata>

<ocr_content>
{content}
</ocr_content>

<available_options>
{options_json}
</available_options>"""


def build_categorization_prompt(
    *,
    content: str,
    available_options: AvailableOptions,
    current_metadata: CurrentMetadata,
    attachment: DocumentAttachment | None = None,
) -> str:
    """Build a full categorization prompt with instructions first, then inline data."""
    attachment_block = _format_attachment_block(attachment)
    categorization_data = build_embedded_categorization_data(
        content=content,
        available_options=available_options,
        current_metadata=current_metadata,
    )
    return f"""{build_categorization_preamble()}

{attachment_block}{categorization_data}"""


def _format_attachment_block(attachment: DocumentAttachment | None) -> str:
    if attachment is None:
        return ""
    return f"""<document_attachment>
path: @{attachment.path}
source: {attachment.source}
mime_type: {attachment.mime_type}
filename: {attachment.filename}
</document_attachment>

"""
