"""Tests for agent debug output."""

from io import StringIO

from rich.console import Console

from llm.debug import _raw_agent_response, format_usage_metadata, print_agent_debug_traces
from llm.schemas import AgentDebugTrace, AvailableOptions, CategorizationAgentOutput, EntityOption
from llm.usage import AgentUsageMetadata


def test_print_agent_debug_traces_renders_prompt_and_raw_output():
    output = StringIO()
    console = Console(file=output, width=120)
    trace = AgentDebugTrace(
        attempt=1,
        prompt="Categorize this document.",
        prepared_content_chars=120,
        ocr_preview="Invoice from Acme",
        available_options=AvailableOptions(
            document_types=[EntityOption(id=10, name="Invoice")],
            tags=[EntityOption(id=2, name="financial")],
        ),
        json_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        command=["codex", "exec"],
        stdout='{"title":"Test"}',
        parsed_payload={"title": "Test"},
        validated_output=CategorizationAgentOutput(title="Test"),
    )

    print_agent_debug_traces(console, [trace], document_id=42)

    rendered = output.getvalue()
    assert "Categorize this document." in rendered
    assert '{"title":"Test"}' in rendered
    assert "Agent output:" not in rendered
    assert "Available options:" not in rendered


def test_raw_agent_response_prefers_output_file():
    trace = AgentDebugTrace(
        attempt=1,
        prompt="prompt",
        prepared_content_chars=1,
        ocr_preview="x",
        available_options=AvailableOptions(),
        json_schema={},
        stdout='{"title":"from stdout"}',
        output_file_content='{"title":"from file"}',
    )

    assert _raw_agent_response(trace) == '{"title":"from file"}'


def test_print_agent_debug_traces_shows_usage_metadata():
    output = StringIO()
    console = Console(file=output, width=120)
    trace = AgentDebugTrace(
        attempt=1,
        prompt="prompt",
        prepared_content_chars=1,
        ocr_preview="x",
        available_options=AvailableOptions(),
        json_schema={},
        usage_metadata=AgentUsageMetadata(
            provider="openai",
            model="gpt-5.4-mini",
            total_tokens=657,
            session_id="sess-1",
        ),
        stdout='{"title":"Test"}',
    )

    print_agent_debug_traces(console, [trace])

    rendered = output.getvalue()
    assert "--- metadata ---" in rendered
    assert "model: gpt-5.4-mini" in rendered
    assert "tokens: 657" in rendered
    assert "session: sess-1" in rendered


def test_format_usage_metadata_includes_cost_and_token_breakdown():
    lines = format_usage_metadata(
        AgentUsageMetadata(
            input_tokens=1000,
            output_tokens=250,
            total_cost_usd=0.0042,
            duration_ms=900,
        )
    )

    assert "tokens: 1,250 (input: 1,000, output: 250)" in lines
    assert "cost: $0.0042" in lines
    assert "duration: 900 ms" in lines
