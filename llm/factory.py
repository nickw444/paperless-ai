"""Factory helpers for constructing the configured LLM agent."""

from __future__ import annotations

from config.settings import settings
from llm.base import CommandLineAgent
from llm.claude import ClaudeClient
from llm.codex import CodexClient


def create_agent(*, debug: bool = False) -> CommandLineAgent:
    """Instantiate the configured agent implementation."""
    provider = settings.ai_agent.lower()

    if provider == "codex":
        return CodexClient(debug=debug)

    if provider == "claude":
        return ClaudeClient(debug=debug)

    raise ValueError(f"Unsupported AI agent provider '{settings.ai_agent}'")
