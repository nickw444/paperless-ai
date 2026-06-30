"""Tests for CLI JSON envelope parsing."""

import json

import pytest

from llm.parsing import extract_claude_structured_output, extract_codex_structured_output


def test_claude_extract_structured_output_flat_envelope():
    stdout = json.dumps(
        {
            "structured_output": {
                "title": "Test Doc",
                "tags": [],
            }
        }
    )

    payload = extract_claude_structured_output(stdout)

    assert payload == {"title": "Test Doc", "tags": []}


def test_claude_extract_structured_output_array_envelope():
    stdout = json.dumps(
        [
            {"type": "message", "content": "working"},
            {
                "type": "result",
                "structured_output": {
                    "title": "From array",
                    "tags": ["financial"],
                },
            },
        ]
    )

    payload = extract_claude_structured_output(stdout)

    assert payload["title"] == "From array"
    assert payload["tags"] == ["financial"]


def test_claude_extract_structured_output_missing_raises():
    with pytest.raises(ValueError, match="Missing structured_output"):
        extract_claude_structured_output(json.dumps({"result": "plain text"}))


def test_codex_read_output_file(tmp_path):
    output_file = tmp_path / "output.json"
    output_file.write_text(
        json.dumps(
            {
                "title": "Codex result",
                "tags": ["utilities"],
            }
        ),
        encoding="utf-8",
    )

    payload = extract_codex_structured_output(str(output_file))

    assert payload["title"] == "Codex result"


def test_codex_read_output_file_empty_raises(tmp_path):
    output_file = tmp_path / "empty.json"
    output_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        extract_codex_structured_output(str(output_file))
