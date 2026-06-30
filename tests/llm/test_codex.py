"""Tests for Codex agent helpers."""

import json
from pathlib import Path

import pytest

from llm.codex import CodexAgent, _read_structured_output


def test_read_structured_output_reads_json_file(tmp_path: Path):
    output_path = tmp_path / "output.json"
    output_path.write_text(
        json.dumps({"title": "Invoice", "tag_ids": [1]}),
        encoding="utf-8",
    )

    payload = _read_structured_output(str(output_path))

    assert payload == {"title": "Invoice", "tag_ids": [1]}


def test_read_structured_output_empty_file_raises(tmp_path: Path):
    output_path = tmp_path / "output.json"
    output_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        _read_structured_output(str(output_path))


def test_read_structured_output_non_object_raises(tmp_path: Path):
    output_path = tmp_path / "output.json"
    output_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(ValueError, match="not a JSON object"):
        _read_structured_output(str(output_path))


def test_build_command_assembles_codex_exec_args():
    agent = CodexAgent.__new__(CodexAgent)
    agent.command = "codex"
    agent.model = "gpt-5.4-mini"
    agent.reasoning_effort = "low"

    command, extra_kwargs = agent._build_command(
        prompt="categorize this",
        schema_path="/tmp/schema.json",
        output_path="/tmp/output.json",
    )

    assert command == [
        "codex",
        "exec",
        "--model",
        "gpt-5.4-mini",
        "--config",
        'model_reasoning_effort="low"',
        "--output-schema",
        "/tmp/schema.json",
        "-o",
        "/tmp/output.json",
        "-",
    ]
    assert extra_kwargs == {"input": "categorize this"}


def test_build_command_omits_reasoning_effort_when_unset():
    agent = CodexAgent.__new__(CodexAgent)
    agent.command = "codex"
    agent.model = "gpt-5"
    agent.reasoning_effort = None

    command, _ = agent._build_command(
        prompt="prompt",
        schema_path="/tmp/schema.json",
        output_path="/tmp/output.json",
    )

    assert "--config" not in command
