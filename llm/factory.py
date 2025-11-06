"""Factory helpers for constructing the configured LLM agent."""

from __future__ import annotations

from config.settings import settings
from llm.base import CommandLineAgent
from llm.claude import ClaudeClient
from llm.codex import CodexClient
from llm.opencode import OpencodeClient


def create_agent() -> CommandLineAgent:
    """Instantiate the configured agent implementation."""
    provider = settings.ai_agent.lower()

    if provider == "codex":
        return CodexClient()

    if provider == "claude":
        return ClaudeClient()

    if provider == "opencode":
        return OpencodeClient()

    raise ValueError(f"Unsupported AI agent provider '{settings.ai_agent}'")
