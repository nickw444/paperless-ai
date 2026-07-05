# paperless-ai

Automated document categorization for Paperless-ngx using the OpenAI Codex CLI.

## What it does

paperless-ai analyzes documents in your Paperless-ngx inbox and suggests appropriate metadata (titles, document dates, tags, correspondents, document types, and storage paths). It can also ask Codex to produce improved document OCR content for Paperless. It uses the Codex CLI to read OCR content and, when possible, supported source document attachments for clearer context.

By using the Codex CLI instead of a direct API, you can process documents using the subscriptions you already have (for example ChatGPT Plus) without paying per-token API costs. This makes it economical to categorize large batches of documents.

## Purpose

Manually categorizing documents in Paperless-ngx is time-consuming. This tool automates the process by:

- Analyzing document content using the Codex CLI
- Suggesting corrected OCR content for Paperless' document content field
- Suggesting metadata based on your existing tags, correspondents, types, and storage paths
- Learning your organizational patterns by matching against existing entities
- Creating new correspondents when needed with automatic matching disabled
- Allowing review before applying changes
- Avoiding API token costs by leveraging the Codex CLI instead of direct APIs

## How it works

1. **Fetch documents**: Retrieves uncategorized documents from your Paperless-ngx inbox
2. **Analyze content**: Sends OCR text, supported document attachments, and your available metadata options to Codex
3. **Generate suggestions**: Codex returns JSON validated against a schema, preferring existing entities and optionally supplying corrected OCR content
4. **Review**: Displays suggestions in a formatted table for your review
5. **Apply changes**: Optionally updates documents in Paperless-ngx and tags them as processed

The tool preserves important workflows like the inbox tag and adds a `paperless-ai-parsed` tag to track which documents have been processed.

## Installation

Requires Python 3.13+. Install dependencies using uv:

```bash
uv sync --dev
```

## Configuration

Create a YAML application config:

```bash
cp config.example.yaml config.yaml
```

Then edit `config.yaml`:

```yaml
paperless:
  url: http://your-paperless-instance

codex:
  command: codex
  model: gpt-5
  timeout: 120
  max_content_chars: 2000
  reasoning_effort: minimal

processing:
  delay_between_documents_seconds: 0
  backfill_comparison_version: "1"

attachments:
  enabled: true
  max_bytes: 20000000
  supported_mime_types:
    - application/pdf
    - image/jpeg
    - image/png

metadata_guidance:
  tags:
    Example Tag:
      use_when: When the document clearly matches this tag.
      avoid_when: When the tag would only apply incidentally.
    Manual Review:
      use_when: When the document needs human review.
      avoid_when: When the document can be safely filed without review.
      protected: true
  document_types:
    Example Type:
      use_when: When the document fits this category.
      avoid_when: When another document type is a better fit.
  storage_paths:
    Example Path:
      use_when: When documents should be stored in this Paperless path.
      avoid_when: When another storage path is more appropriate.
```

Keep private tokens in `.env` or the process environment:

```bash
PAPERLESS_API_TOKEN=your-api-token
```

`config.yaml` is loaded by default. To use a different file, set `PAPERLESS_AI_CONFIG_FILE`.

### CLI version requirements

Codex responses are JSON-only, enforced by schema at invocation time. Requires Codex CLI with `exec --output-schema` support.

### Metadata guidance

paperless-ai offers only the configured tags, document types, and storage paths in
`metadata_guidance` to Codex. This keeps categorization choices deliberate and gives
the model concrete rules for each option.

Tags omitted from `metadata_guidance.tags` are not visible to Codex and are preserved
if already present on a document, so Codex cannot add or remove them.

Tags marked `protected: true` are still available to Codex, so they can be added when
relevant. If a protected tag is already present on a document, paperless-ai preserves it
even when Codex omits it from the suggested tag IDs.

Tags marked `deprecated: true` are not visible to Codex and are not preserved. If a
deprecated tag is already present on a document, paperless-ai removes it when applying
the suggestion.

## Usage

Test connection to Paperless:
```bash
python main.py test-connection
```

List documents in inbox:
```bash
python main.py list-inbox
```

Analyze documents and show suggestions:
```bash
python main.py analyze
```

Process documents in batches:
```bash
python main.py analyze --limit 10
```

Analyze documents matching a Paperless query, including non-inbox documents:
```bash
python main.py analyze --query "tag:Bill" --limit 10
```

Analyze a specific document:
```bash
python main.py analyze --id 123
```

Reprocess inbox documents whose stored paperless-ai backfill comparison version differs from config:
```bash
python main.py analyze --reprocess-stale
```

Reprocess all inbox documents, including documents already marked parsed:
```bash
python main.py analyze --reprocess-all
```

Inspect raw agent input and output:
```bash
python main.py analyze --id 123 --debug
```

Export suggestions to JSON:
```bash
python main.py analyze --export suggestions.json
```

## Features

- **Intelligent matching**: Codex tries to match existing entities before suggesting new ones
- **Correspondent creation**: Suggests new correspondents when none match, with automatic matching disabled
- **Document date suggestions**: Suggests Date Created updates when document content supports a more reliable date
- **LLM OCR content**: Optionally applies Codex-produced replacement document content
- **Batch processing**: Process documents incrementally with `--limit`
- **Incremental workflow**: Already-processed documents are automatically excluded
- **Backfill workflow**: Reprocess parsed documents whose stored backfill comparison version differs from config, or target documents with a Paperless query
- **Processing metadata**: Writes model, backfill comparison marker, and token JSON to Paperless custom fields
- **Processing delay**: Optionally delay between document analyses with `processing.delay_between_documents_seconds`
- **Protected tag preservation**: Keeps `protected: true` guided tags for manual review workflows
- **Lifecycle tag ownership**: Omits `paperless-ai-parsed` and `paperless-ai-failed` from agent choices
- **JSON export**: Save suggestions for later review or automation
- **Debug mode**: Print raw agent prompts, responses, and available token/cost metadata
- **Document attachments**: Adds supported PDF/JPEG/PNG document files alongside OCR context where available

## Development

Lint code:
```bash
uv run ruff check .
```

Format code:
```bash
uv run ruff format .
```

Run tests:
```bash
uv run pytest tests/
```
