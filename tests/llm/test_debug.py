"""Tests for agent debug output."""

from io import StringIO

from rich.console import Console

from llm.base import AgentDebugTrace
from llm.debug import format_usage_metadata, print_agent_debug_traces
from llm.usage import AgentUsageMetadata


def test_print_agent_debug_traces_renders_prompt_and_raw_output():
    output = StringIO()
    console = Console(file=output, width=120)
    trace = AgentDebugTrace(
        attempt=1,
        prompt="Prompt with @/tmp/file.txt",
        resolved_prompt="Prompt with inline file contents",
        stdout="TITLE: Test\nTYPE: None",
    )

    print_agent_debug_traces(console, [trace], document_id=42)

    rendered = output.getvalue()
    assert "Prompt with inline file contents" in rendered
    assert "@/tmp/file.txt" not in rendered
    assert "TITLE: Test" in rendered


def test_print_agent_debug_traces_shows_usage_metadata():
    output = StringIO()
    console = Console(file=output, width=120)
    trace = AgentDebugTrace(
        attempt=1,
        prompt="prompt",
        stdout="TITLE: Test",
        usage_metadata=AgentUsageMetadata(
            provider="openai",
            model="gpt-5.4-mini",
            session_id="sess-1",
            total_tokens=657,
        ),
    )

    print_agent_debug_traces(console, [trace])

    rendered = output.getvalue()
    assert "--- metadata ---" in rendered
    assert "provider: openai" in rendered
    assert "model: gpt-5.4-mini" in rendered
    assert "session: sess-1" in rendered
    assert "tokens: 657" in rendered


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
