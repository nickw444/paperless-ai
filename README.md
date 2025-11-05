# paperless-ai

Automated document categorization for Paperless-ngx using CLI-based AI agents (Claude Code by default, with optional Codex support).

## What it does

paperless-ai analyzes documents in your Paperless-ngx inbox and suggests appropriate metadata (titles, tags, correspondents, document types, and storage paths). It integrates with CLI tooling to read OCR content and make intelligent categorization decisions based on your existing Paperless setup. Claude Code remains the default integration, and the Codex CLI can be enabled when preferred.

By using a CLI agent instead of a direct API, you can process documents using the subscriptions you already have (for example Claude Pro) without paying per-token API costs. This makes it economical to categorize large batches of documents.

## Purpose

Manually categorizing documents in Paperless-ngx is time-consuming. This tool automates the process by:

- Analyzing document content using the configured agent (Claude by default)
- Suggesting metadata based on your existing tags, correspondents, types, and storage paths
- Learning your organizational patterns by matching against existing entities
- Creating new correspondents when needed (with ML matching enabled)
- Allowing review before applying changes
- Avoiding API token costs by leveraging CLI agents instead of direct APIs

## How it works

1. **Fetch documents**: Retrieves uncategorized documents from your Paperless-ngx inbox
2. **Analyze content**: Sends OCR text to the configured agent along with your available metadata options
3. **Generate suggestions**: The agent suggests appropriate categorizations, preferring existing entities
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

# Agent selection (default: claude)
AI_AGENT=claude        # or codex (required when using Codex CLI)

# Claude configuration
CLAUDE_COMMAND=claude  # Path to Claude CLI
CLAUDE_MODEL=sonnet    # Optional override
CLAUDE_TIMEOUT=120     # Timeout in seconds

# Codex configuration (used when AI_AGENT=codex)
CODEX_COMMAND=codex
CODEX_MODEL=gpt-5          # Optional, defaults to gpt-5
CODEX_TIMEOUT=120
CODEX_REASONING_EFFORT=minimal
```

Both agents share the same `CLAUDE_MAX_CONTENT_CHARS` setting by default; set `CODEX_MAX_CONTENT_CHARS` if you need a different limit when using Codex.

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

Analyze with review and apply:
```bash
python main.py analyze --apply
```

Process documents in batches:
```bash
python main.py analyze --limit 10 --apply
```

Analyze a specific document:
```bash
python main.py analyze --id 123
```

Export suggestions to JSON:
```bash
python main.py analyze --export suggestions.json
```

## Features

- **Intelligent matching**: The LLM agent tries to match existing entities before suggesting new ones
- **Correspondent creation**: Suggests new correspondents when none match, with ML auto-matching enabled
- **Batch processing**: Process documents incrementally with `--limit`
- **Incremental workflow**: Already-processed documents are automatically excluded
- **Inbox preservation**: Keeps inbox tags for manual review workflows
- **JSON export**: Save suggestions for later review or automation

## Development

Lint code:
```bash
uv run ruff check .
```

Format code:
```bash
uv run ruff format .
```
