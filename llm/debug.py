"""Debug console output for agent invocations."""

from __future__ import annotations

from rich.console import Console

from llm.schemas import AgentDebugTrace
from llm.usage import AgentUsageMetadata, extract_usage


def print_agent_debug_traces(
    console: Console,
    traces: list[AgentDebugTrace],
    *,
    document_id: int | None = None,
) -> None:
    """Print raw agent prompts and responses for inspection."""
    if not traces:
        return

    header = f"Agent debug: document {document_id}" if document_id else "Agent debug"
    console.print(f"\n[bold magenta]{header}[/bold magenta]")

    for trace in traces:
        if len(traces) > 1:
            console.print(f"\n[bold]Attempt {trace.attempt}[/bold]")
        if trace.error:
            console.print(f"[red]Error:[/red] {trace.error}")

        usage = trace.usage_metadata or extract_usage(trace.stderr, trace.command)
        if usage and usage.has_displayable_fields():
            console.print("\n[dim]--- metadata ---[/dim]")
            for line in format_usage_metadata(usage):
                console.print(line)

        console.print("\n[dim]--- prompt ---[/dim]")
        console.print(trace.prompt)

        raw_output = _raw_agent_response(trace)
        if raw_output:
            console.print("\n[dim]--- output ---[/dim]")
            console.print(raw_output)


def format_usage_metadata(usage: AgentUsageMetadata) -> list[str]:
    """Format usage metadata as human-readable lines."""
    lines: list[str] = []

    if usage.provider:
        lines.append(f"provider: {usage.provider}")
    if usage.model:
        lines.append(f"model: {usage.model}")
    if usage.session_id:
        lines.append(f"session: {usage.session_id}")
    if usage.reasoning_effort:
        lines.append(f"reasoning effort: {usage.reasoning_effort}")

    token_line = _format_token_line(usage)
    if token_line:
        lines.append(token_line)

    if usage.total_cost_usd is not None:
        lines.append(f"cost: ${usage.total_cost_usd:.4f}")
    if usage.duration_ms is not None:
        lines.append(f"duration: {usage.duration_ms} ms")
    if usage.num_turns is not None:
        lines.append(f"turns: {usage.num_turns}")

    for key, value in sorted(usage.extra.items()):
        if key in _SKIP_EXTRA_METADATA:
            continue
        lines.append(f"{key}: {value}")

    return lines


_SKIP_EXTRA_METADATA = frozenset(
    {"approval", "reasoning summaries", "sandbox", "workdir"},
)


def _format_token_line(usage: AgentUsageMetadata) -> str | None:
    if usage.input_tokens is not None or usage.output_tokens is not None:
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        total = (
            usage.total_tokens if usage.total_tokens is not None else input_tokens + output_tokens
        )
        return f"tokens: {total:,} (input: {input_tokens:,}, output: {output_tokens:,})"

    if usage.total_tokens is not None:
        return f"tokens: {usage.total_tokens:,}"

    return None


def _raw_agent_response(trace: AgentDebugTrace) -> str:
    if trace.output_file_content and trace.output_file_content.strip():
        return trace.output_file_content
    return trace.stdout
