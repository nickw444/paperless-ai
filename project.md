# Paperless-AI: Automated Document Categorization Tool

A command line tool to categorize Paperless-ngx documents in the inbox queue using the Codex CLI.

## Overview

This tool automates the naming and tagging of documents in Paperless-ngx by analyzing their OCR content with the OpenAI Codex CLI (`codex exec`).

**IMPORTANT**: Phase 1 is READ-ONLY. The tool will analyze documents and suggest categorizations but will NOT make any changes to Paperless. This allows for safe testing and verification before enabling write mode in Phase 2.

## Quick Start

1. Create `.env` file with your Paperless credentials
2. Install dependencies: `uv sync --dev`
3. Test connection: `paperless-ai test-connection`
4. Analyze inbox: `paperless-ai analyze`

## Technical Details

- **Language**: Python 3.13+
- **Package Manager**: uv
- **Dependencies**: python-dotenv for environment variable management
- **Paperless API**: https://docs.paperless-ngx.com/api/ (remote instance)
- **Architecture**: Modular design with separate components for each concern
- **Mode**: READ-ONLY for Phase 1 (no document updates)

## Project Structure

```
paperless-ai/
├── main.py                 # CLI entry point
├── paperless/              # Paperless-ngx API interaction
│   ├── __init__.py
│   ├── client.py          # API client
│   └── models.py          # Data models
├── llm/                    # Codex CLI agent
│   ├── __init__.py
│   ├── codex.py          # CodexAgent implementation
│   ├── prompts.py        # Prompt templates
│   ├── schemas.py        # Models and validation
│   ├── usage.py          # Token/cost metadata parsing
│   └── debug.py          # Debug console output
├── categorizer/           # Core categorization logic
│   ├── __init__.py
│   └── engine.py         # Orchestrates the categorization process
└── config/                # Configuration management
    ├── __init__.py
    └── settings.py       # Settings and environment variables
```

## Phase 1: Basic Implementation

### 1. Paperless API Client (`paperless/client.py`)
- [ ] Implement authentication (API token from environment variable)
- [ ] Handle remote instance connection with proper headers
- [ ] List all documents with status="inbox"
- [ ] Fetch document content (OCR text) by ID
- [ ] Fetch all available:
  - [ ] Tags
  - [ ] Document types
  - [ ] Correspondents
  - [ ] Storage paths
- [ ] ~~Update document metadata~~ (DISABLED in Phase 1 - read-only mode)

### 2. Codex CLI Agent (`llm/codex.py`)
- [ ] Build prompt with inline OCR content and available options
- [ ] Execute Codex via subprocess (`codex exec` with stdin prompt)
- [ ] Validate JSON agent response against schema
- [ ] Clean up temp files after processing
- [ ] Handle errors and timeouts
- [ ] Implement retry logic

### 3. Categorization Engine (`categorizer/engine.py`)
- [ ] Build prompt template with:
  - Document OCR content
  - Available tags, types, correspondents
  - Instructions for categorization
- [ ] Parse Codex categorization response
- [ ] Map agent suggestions to Paperless entities
- [ ] Display suggested changes (read-only mode)
- [ ] ~~Apply changes to document via API~~ (DISABLED in Phase 1)

### 4. CLI Interface (`main.py`)
- [ ] Command: `paperless-ai analyze` - Analyze all inbox documents (READ-ONLY)
- [ ] Command: `paperless-ai analyze --id <doc_id>` - Analyze specific document
- [ ] Command: `paperless-ai list-inbox` - List inbox documents
- [ ] Command: `paperless-ai test-connection` - Verify Paperless connection
- [ ] Options:
  - `--output <format>` - Output format (json, table, csv)
  - `--limit <n>` - Process only first N documents
  - `--export <file>` - Export suggestions to file

## Configuration

### Environment Variables (.env file)
Use python-dotenv to load environment variables from `.env` file:

```env
# Remote Paperless instance
PAPERLESS_URL=https://your-paperless-instance.com
PAPERLESS_API_TOKEN=your-api-token-here

# Codex CLI configuration
CODEX_COMMAND=codex  # Path to Codex CLI if not in PATH
CODEX_MODEL=gpt-5
CODEX_TIMEOUT=120
CODEX_MAX_CONTENT_CHARS=2000
CODEX_REASONING_EFFORT=minimal
```

The application should:
1. Check for .env file in project root
2. Load variables using python-dotenv
3. Validate required variables on startup
4. Provide clear error messages for missing configuration

## Codex Prompt Template

The tool embeds OCR content and available options directly in the prompt sent to Codex via stdin:

```bash
codex exec --model gpt-5 --output-schema /tmp/schema.json -o /tmp/output.json - <<'EOF'
You are helping categorize a document in Paperless-ngx.

<current_metadata>...</current_metadata>
<ocr_content>...</ocr_content>
<available_options>...</available_options>
EOF
```

Implementation notes:
- Use Python's `tempfile.NamedTemporaryFile` for schema and output files only
- Ensure proper cleanup even on errors (use try/finally)
- Generate unique filenames to avoid conflicts with parallel processing

## Output Format (Read-Only Mode)

For each analyzed document, display:
```
Document ID: 123
Current Title: "scan_2024_01_15.pdf"
Suggested Title: "Invoice - Acme Corp - January 2024"
Current Type: None
Suggested Type: "Invoice"
Current Tags: []
Suggested Tags: ["financial", "2024", "acme-corp"]
Current Correspondent: None
Suggested Correspondent: "Acme Corporation"
Status: ✓ Analyzed successfully
```

## Error Handling

- Network failures: Retry with exponential backoff
- Invalid Codex responses: Log and skip document
- Missing OCR content: Skip document with warning
- API authentication failures: Exit with clear error message
- Connection timeouts: Configurable timeout with retry

## Testing Strategy

1. Unit tests for each module
2. Mock Paperless API responses
3. Mock Codex CLI responses
4. Integration test with test Paperless instance

## Future Enhancements (Not in Phase 1)

- Direct OpenAI API integration when needed
- Batch processing with progress bar
- Learning from user corrections
- Custom categorization rules
- Web UI for reviewing suggestions
- Webhook support for automatic processing

## Success Criteria (Phase 1 - Read-Only)

- Successfully connects to remote Paperless-ngx API using token authentication
- Retrieves and lists all inbox documents
- Fetches OCR content for each document
- Generates appropriate categorization suggestions via Codex CLI
- Displays suggestions clearly without modifying documents
- Handles errors gracefully with informative messages
- Exports suggestions to file for review
- Validates all environment variables on startup

## Required Dependencies

Add to `pyproject.toml`:
```toml
[project]
dependencies = [
    "python-dotenv>=1.0.0",
    "requests>=2.31.0",
    "click>=8.1.0",  # For CLI interface
    "rich>=13.0.0",   # For pretty console output
    "pydantic>=2.0.0", # For data validation
]
```

## Phase 2: Write Mode (Future)

Once the read-only mode is verified to work correctly:
- Add `--apply` flag to actually update documents
- Implement confirmation prompts
- Add rollback/undo functionality
- Log all changes for audit trail

## Security Notes

- Never commit `.env` file (add to .gitignore)
- API token should have appropriate permissions in Paperless
- Use HTTPS for remote connections
- Consider rate limiting to avoid overwhelming the Codex CLI

## Paperless-ngx REST API Reference

### Authentication

Use Token Authentication for API access:
1. Generate an API token in Paperless user profile
2. Include in all requests: `Authorization: Token <your-token-here>`

### Key Endpoints

#### List Documents
```
GET /api/documents/
```
Query parameters:
- `?query=<search_term>` - Full text search
- `?tags__id__in=<tag_id>` - Filter by tag ID
- `?correspondent__id=<id>` - Filter by correspondent
- `?document_type__id=<id>` - Filter by document type
- `?is_in_inbox=true` - Get only inbox documents (unprocessed)
- `?page=<n>` - Pagination
- `?page_size=<n>` - Results per page (default 25)
- `?ordering=-created` - Sort by creation date (newest first)

Example request:
```python
headers = {"Authorization": "Token YOUR_TOKEN"}
response = requests.get(
    f"{PAPERLESS_URL}/api/documents/?is_in_inbox=true",
    headers=headers
)
```

#### Get Document Details
```
GET /api/documents/{id}/
```
Returns document metadata including:
- id, title, content (OCR text)
- correspondent, document_type, storage_path
- tags (list of tag IDs)
- created, modified, added dates
- original_file_name, archived_file_name

#### Download Document Content
```
GET /api/documents/{id}/download/
GET /api/documents/{id}/preview/  # For rendered preview
GET /api/documents/{id}/thumb/    # For thumbnail
```

#### Get Document Text/OCR Content
The OCR content is included in the document details response:
```python
doc = requests.get(f"{PAPERLESS_URL}/api/documents/{id}/", headers=headers).json()
ocr_content = doc["content"]  # This is the OCR text
```

#### List Tags
```
GET /api/tags/
```
Returns all available tags with:
- id, name, slug
- color, text_color (hex values)
- match, matching_algorithm
- is_inbox_tag, document_count

#### List Correspondents
```
GET /api/correspondents/
```
Returns:
- id, name, slug
- match, matching_algorithm
- is_insensitive, document_count

#### List Document Types
```
GET /api/document_types/
```
Returns:
- id, name, slug
- match, matching_algorithm
- is_insensitive, document_count

#### Update Document (Phase 2 - Future)
```
PATCH /api/documents/{id}/
```
Request body (JSON):
```json
{
    "title": "New Title",
    "correspondent": 5,  // ID or null
    "document_type": 2,  // ID or null
    "tags": [1, 3, 7]    // Array of tag IDs
}
```

### Response Format

Documents list response:
```json
{
    "count": 150,
    "next": "http://paperless/api/documents/?page=2",
    "previous": null,
    "all": [1, 2, 3, ...],  // All matching document IDs
    "results": [
        {
            "id": 123,
            "correspondent": 5,
            "document_type": 2,
            "storage_path": null,
            "title": "Invoice 2024",
            "content": "OCR text content here...",
            "tags": [1, 3],
            "created": "2024-01-15T10:30:00Z",
            "created_date": "2024-01-15",
            "modified": "2024-01-16T14:20:00Z",
            "added": "2024-01-15T10:30:00Z",
            "archive_serial_number": null,
            "original_file_name": "scan.pdf",
            "archived_file_name": "2024-01-15 Invoice.pdf",
            "owner": 1,
            "user_can_change": true,
            "is_shared_by_requester": false,
            "notes": [],
            "custom_fields": []
        }
    ]
}
```

### Implementation Notes

1. **Pagination**: Always handle pagination when listing documents
2. **Error Handling**: Check for 401 (auth), 404 (not found), 500 (server error)
3. **Rate Limiting**: No explicit rate limits documented, but implement reasonable delays
4. **Inbox Filter**: Use `is_in_inbox=true` to get only unprocessed documents
5. **Content Field**: The `content` field in document response contains the full OCR text
6. **IDs vs Names**: API uses numeric IDs for relationships (tags, types, correspondents)
