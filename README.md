# paperless-ai

Automated document categorization for Paperless-ngx using the OpenAI Codex CLI.

## What it does

paperless-ai analyzes documents in your Paperless-ngx inbox and suggests appropriate metadata (titles, tags, correspondents, document types, and storage paths). It can also ask Codex to produce improved document OCR content for Paperless. It uses the Codex CLI to read OCR content and, when possible, supported source document attachments for clearer context.

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

Create a `.env` file or set environment variables:

```bash
PAPERLESS_URL=http://your-paperless-instance
PAPERLESS_API_TOKEN=your-api-token

# Codex configuration
CODEX_COMMAND=codex
CODEX_MODEL=gpt-5          # Optional, defaults to gpt-5
CODEX_TIMEOUT=120
CODEX_MAX_CONTENT_CHARS=2000
CODEX_REASONING_EFFORT=minimal

# Document attachments
ENABLE_DOCUMENT_ATTACHMENTS=true
MAX_ATTACHMENT_BYTES=20000000
SUPPORTED_ATTACHMENT_MIME_TYPES=application/pdf,image/jpeg,image/png

# Protected tags
PROTECTED_TAGS=Inbox,From Email,Tax Deduction

# Processing metadata custom fields
PAPERLESS_AI_PROCESSING_VERSION=1
PAPERLESS_AI_VERSION_FIELD_NAME=paperless-ai-version
PAPERLESS_AI_MODEL_FIELD_NAME=paperless-ai-model
PAPERLESS_AI_TOKENS_FIELD_NAME=paperless-ai-tokens
```

### CLI version requirements

Codex responses are JSON-only, enforced by schema at invocation time. Requires Codex CLI with `exec --output-schema` support.

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

Analyze a specific document:
```bash
python main.py analyze --id 123
```

Reprocess inbox documents whose stored paperless-ai version is stale:
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
- **LLM OCR content**: Optionally applies Codex-produced replacement document content
- **Batch processing**: Process documents incrementally with `--limit`
- **Incremental workflow**: Already-processed documents are automatically excluded
- **Backfill workflow**: Reprocess stale or all parsed inbox documents with explicit flags
- **Processing metadata**: Writes model, processing version, and token JSON to Paperless custom fields
- **Protected tag preservation**: Keeps configured protected tags for manual review workflows
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
