"""Tests for Codex agent helpers."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from llm.codex import CodexAgent, _read_structured_output
from llm.schemas import AvailableOptions, CurrentMetadata, EntityOption
from paperless.models import DocumentAttachment


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


def test_build_command_adds_image_attachment_flag():
    agent = CodexAgent.__new__(CodexAgent)
    agent.command = "codex"
    agent.model = "gpt-5.4-mini"
    agent.reasoning_effort = None

    command, _ = agent._build_command(
        prompt="prompt",
        schema_path="/tmp/schema.json",
        output_path="/tmp/output.json",
        attachment=DocumentAttachment(
            path="/tmp/source.png",
            source="original",
            mime_type="image/png",
            filename="source.png",
        ),
    )

    assert "--image" in command
    assert command[command.index("--image") + 1] == "/tmp/source.png"


def test_build_command_does_not_add_image_flag_for_pdf_attachment():
    agent = CodexAgent.__new__(CodexAgent)
    agent.command = "codex"
    agent.model = "gpt-5"
    agent.reasoning_effort = None

    command, _ = agent._build_command(
        prompt="prompt",
        schema_path="/tmp/schema.json",
        output_path="/tmp/output.json",
        attachment=DocumentAttachment(
            path="/tmp/source.pdf",
            source="archived",
            mime_type="application/pdf",
            filename="source.pdf",
        ),
    )

    assert "--image" not in command


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


def _make_agent(**overrides) -> CodexAgent:
    agent = CodexAgent.__new__(CodexAgent)
    agent.timeout = overrides.get("timeout", 30)
    agent.max_content_chars = overrides.get("max_content_chars", 2000)
    agent.max_retries = overrides.get("max_retries", 1)
    agent.debug = overrides.get("debug", False)
    agent.command = overrides.get("command", "codex")
    agent.model = overrides.get("model", "gpt-5")
    agent.reasoning_effort = overrides.get("reasoning_effort")
    return agent


def _sample_options() -> AvailableOptions:
    return AvailableOptions(
        document_types=[EntityOption(id=10, name="Invoice")],
        tags=[EntityOption(id=2, name="financial")],
        correspondents=[EntityOption(id=5, name="Acme Corp")],
    )


def _sample_metadata() -> CurrentMetadata:
    return CurrentMetadata(title="scan.pdf")


def test_categorize_document_runs_codex_subprocess_and_validates_output():
    agent = _make_agent()
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        output_path = command[command.index("-o") + 1]
        captured["command"] = command
        captured["input"] = kwargs.get("input")
        payload = {
            "title": "Invoice - Acme",
            "document_type_id": 10,
            "tag_ids": [2],
            "correspondent_id": 5,
            "new_correspondent_name": None,
            "storage_path_id": None,
        }
        Path(output_path).write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with patch("llm.codex.subprocess.run", side_effect=fake_run):
        result = agent.categorize_document(
            ocr_content="Invoice from Acme Corp for $100",
            available_options=_sample_options(),
            current_metadata=_sample_metadata(),
            attachment=DocumentAttachment(
                path="/tmp/source.pdf",
                source="archived",
                mime_type="application/pdf",
                filename="source.pdf",
            ),
        )

    assert result.error is None
    assert result.output is not None
    assert result.output.title == "Invoice - Acme"
    assert result.output.document_type_id == 10
    assert result.output.tag_ids == [2]
    assert captured["command"][0] == "codex"
    assert captured["command"][1] == "exec"
    assert "Invoice from Acme Corp" in captured["input"]
    assert "@/tmp/source.pdf" in captured["input"]


def test_categorize_document_returns_error_when_codex_fails():
    agent = _make_agent()

    def fake_run(command, **kwargs):
        del kwargs
        raise subprocess.CalledProcessError(1, command, stderr="codex failed")

    with patch("llm.codex.subprocess.run", side_effect=fake_run):
        result = agent.categorize_document(
            ocr_content="Invoice",
            available_options=_sample_options(),
            current_metadata=_sample_metadata(),
        )

    assert result.output is None
    assert result.error is not None
    assert "exit code 1" in result.error
