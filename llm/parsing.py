"""JSON envelope extraction for CLI agent responses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def extract_claude_structured_output(stdout: str) -> dict[str, Any]:
    """Extract structured_output from Claude CLI JSON stdout."""
    data = json.loads(stdout)

    if isinstance(data, dict) and data.get("structured_output") is not None:
        payload = data["structured_output"]
        if isinstance(payload, dict):
            return payload
        raise ValueError("structured_output is not a JSON object")

    if isinstance(data, list):
        for item in reversed(data):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "result" and item.get("structured_output") is not None:
                payload = item["structured_output"]
                if isinstance(payload, dict):
                    return payload
                raise ValueError("structured_output is not a JSON object")

    raise ValueError("Missing structured_output in Claude JSON response")


def extract_codex_structured_output(output_path: str) -> dict[str, Any]:
    """Read validated JSON output written by Codex CLI."""
    content = Path(output_path).read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Codex output file is empty: {output_path}")

    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("Codex output is not a JSON object")
    return data
