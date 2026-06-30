"""Helpers for working with command-line language model agents."""

from .base import CommandLineAgent
from .schemas import (
    AgentCategorizationResult,
    AvailableOptions,
    CategorizationAgentOutput,
    EntityOption,
    validate_agent_output,
)


def create_agent(*, debug: bool = False) -> CommandLineAgent:
    """Instantiate the configured agent implementation."""
    from .factory import create_agent as _create_agent

    return _create_agent(debug=debug)


__all__ = [
    "AgentCategorizationResult",
    "AvailableOptions",
    "CategorizationAgentOutput",
    "CommandLineAgent",
    "EntityOption",
    "create_agent",
    "validate_agent_output",
]
