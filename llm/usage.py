"""Extract token and cost metadata from CLI agent output."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field


class AgentUsageMetadata(BaseModel):
    """Usage and billing metadata reported by an agent CLI invocation."""

    provider: str | None = None
    model: str | None = None
    session_id: str | None = None
    total_tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int | None = None
    reasoning_effort: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)

    def has_displayable_fields(self) -> bool:
        return any(
            value is not None
            for value in (
                self.provider,
                self.model,
                self.session_id,
                self.total_tokens,
                self.input_tokens,
                self.output_tokens,
                self.total_cost_usd,
                self.duration_ms,
                self.num_turns,
                self.reasoning_effort,
            )
        ) or bool(self.extra)


def extract_agent_usage(
    *,
    stdout: str,
    stderr: str,
    command: list[str],
) -> AgentUsageMetadata | None:
    """Extract usage metadata from provider-specific CLI output."""
    if _is_codex_command(command):
        usage = extract_codex_usage(stderr, command)
        if usage.has_displayable_fields():
            return usage
        return None

    if _is_claude_command(command):
        usage = extract_claude_usage(stdout)
        if usage and usage.has_displayable_fields():
            return usage

    usage = extract_claude_usage(stdout)
    if usage and usage.has_displayable_fields():
        return usage

    usage = extract_codex_usage(stderr, command)
    if usage.has_displayable_fields():
        return usage

    return None


def extract_codex_usage(stderr: str, command: list[str] | None = None) -> AgentUsageMetadata:
    """Parse Codex session metadata and token usage from stderr."""
    metadata = _parse_codex_session_metadata(stderr)
    total_tokens = _parse_codex_total_tokens(stderr)

    usage = AgentUsageMetadata(
        provider=metadata.get("provider"),
        model=metadata.get("model") or _model_from_command(command or []),
        session_id=metadata.get("session id"),
        total_tokens=total_tokens,
        reasoning_effort=metadata.get("reasoning effort"),
    )

    for key, value in metadata.items():
        if key in {"provider", "model", "session id", "reasoning effort"}:
            continue
        usage.extra[key] = value

    return usage


def extract_claude_usage(stdout: str) -> AgentUsageMetadata | None:
    """Parse Claude JSON stdout for usage and cost metadata."""
    if not stdout.strip():
        return None

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict):
        return _claude_usage_from_envelope(data)

    if isinstance(data, list):
        for item in reversed(data):
            if isinstance(item, dict) and item.get("type") == "result":
                return _claude_usage_from_envelope(item)

    return None


def _claude_usage_from_envelope(data: dict[str, object]) -> AgentUsageMetadata:
    usage = data.get("usage")
    input_tokens = None
    output_tokens = None
    total_tokens = None

    if isinstance(usage, dict):
        raw_input = usage.get("input_tokens")
        raw_output = usage.get("output_tokens")
        if isinstance(raw_input, int):
            input_tokens = raw_input
        if isinstance(raw_output, int):
            output_tokens = raw_output
        if input_tokens is not None or output_tokens is not None:
            total_tokens = (input_tokens or 0) + (output_tokens or 0)

    total_cost_usd = data.get("total_cost_usd")
    duration_ms = data.get("duration_ms")
    num_turns = data.get("num_turns")

    return AgentUsageMetadata(
        provider="anthropic",
        model=_string_or_none(data.get("model")),
        session_id=_string_or_none(data.get("session_id")),
        total_tokens=total_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_cost_usd=float(total_cost_usd) if isinstance(total_cost_usd, (int, float)) else None,
        duration_ms=int(duration_ms) if isinstance(duration_ms, int) else None,
        num_turns=int(num_turns) if isinstance(num_turns, int) else None,
    )


def _parse_codex_session_metadata(stderr: str) -> dict[str, str]:
    parts = stderr.split("--------")
    if len(parts) < 2:
        return {}

    fields: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _parse_codex_total_tokens(stderr: str) -> int | None:
    match = re.search(r"(?m)^tokens used\n([\d,]+)\s*$", stderr)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _model_from_command(command: list[str]) -> str | None:
    for index, arg in enumerate(command):
        if arg == "--model" and index + 1 < len(command):
            return command[index + 1]
    return None


def _is_codex_command(command: list[str]) -> bool:
    if not command:
        return False
    executable = Path(command[0]).name.lower()
    return executable == "codex" or (
        len(command) > 1 and command[1] == "exec" and "codex" in executable
    )


def _is_claude_command(command: list[str]) -> bool:
    if not command:
        return False
    return "claude" in Path(command[0]).name.lower()


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
