# paperless-ai

Automated document categorization for Paperless-ngx using Claude AI via the Claude Code CLI.

## What it does

paperless-ai analyzes documents in your Paperless-ngx inbox and suggests appropriate metadata (titles, tags, correspondents, document types, and storage paths). It uses the [Claude Code CLI](https://docs.claude.com/en/docs/claude-code) to read OCR content and make intelligent categorization decisions based on your existing Paperless setup.

By using Claude Code instead of the Claude API, you can process documents without paying per-token costs if you already have a Claude subscription (Pro or other paid plan). This makes it economical to categorize large batches of documents.

## Purpose

Manually categorizing documents in Paperless-ngx is time-consuming. This tool automates the process by:

- Analyzing document content using Claude AI via your existing subscription
- Suggesting metadata based on your existing tags, correspondents, types, and storage paths
- Learning your organizational patterns by matching against existing entities
- Creating new correspondents when needed (with ML matching enabled)
- Allowing review before applying changes
- Avoiding API token costs by leveraging Claude Code

## How it works

1. **Fetch documents**: Retrieves uncategorized documents from your Paperless-ngx inbox
2. **Analyze content**: Sends OCR text to Claude AI along with your available metadata options
3. **Generate suggestions**: Claude suggests appropriate categorizations, preferring existing entities
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
CLAUDE_COMMAND=claude  # Path to Claude CLI
CLAUDE_TIMEOUT=120     # Timeout in seconds
```

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

- **Intelligent matching**: Claude tries to match existing entities before suggesting new ones
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
