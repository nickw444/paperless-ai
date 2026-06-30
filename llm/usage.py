"""Extract token and cost metadata from Codex CLI output."""

from __future__ import annotations

import re

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


def extract_usage(stderr: str, command: list[str] | None = None) -> AgentUsageMetadata:
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
