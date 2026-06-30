"""Tests for agent usage metadata extraction."""

from llm.usage import (
    AgentUsageMetadata,
    extract_agent_usage,
    extract_claude_usage,
    extract_codex_usage,
)


def test_extract_codex_usage_from_stderr():
    stderr = (
        "OpenAI Codex v0.133.0\n"
        "--------\n"
        "workdir: /tmp/project\n"
        "model: gpt-5.4-mini\n"
        "provider: openai\n"
        "approval: never\n"
        "sandbox: workspace-write\n"
        "reasoning effort: low\n"
        "session id: abc-123\n"
        "--------\n"
        "user\nprompt text\n"
        "codex\nresponse\n"
        "tokens used\n"
        "13,421\n"
    )

    usage = extract_codex_usage(stderr, ["codex", "exec", "--model", "gpt-5.4-mini"])

    assert usage.provider == "openai"
    assert usage.model == "gpt-5.4-mini"
    assert usage.session_id == "abc-123"
    assert usage.total_tokens == 13421
    assert usage.reasoning_effort == "low"
    assert usage.total_cost_usd is None
    assert usage.extra["workdir"] == "/tmp/project"


def test_extract_claude_usage_from_json_stdout():
    stdout = """
    {
      "type": "result",
      "subtype": "success",
      "model": "claude-sonnet-4-20250514",
      "session_id": "sess-42",
      "total_cost_usd": 0.0042,
      "duration_ms": 3210,
      "num_turns": 2,
      "usage": {
        "input_tokens": 1000,
        "output_tokens": 234
      },
      "structured_output": {"title": "Test"}
    }
    """

    usage = extract_claude_usage(stdout)

    assert usage is not None
    assert usage.provider == "anthropic"
    assert usage.model == "claude-sonnet-4-20250514"
    assert usage.session_id == "sess-42"
    assert usage.total_tokens == 1234
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 234
    assert usage.total_cost_usd == 0.0042
    assert usage.duration_ms == 3210
    assert usage.num_turns == 2


def test_extract_agent_usage_selects_provider_from_command():
    codex_usage = extract_agent_usage(
        stdout='{"title":"Test"}',
        stderr="--------\nmodel: gpt-5\nprovider: openai\n--------\ntokens used\n100\n",
        command=["codex", "exec"],
    )
    assert isinstance(codex_usage, AgentUsageMetadata)
    assert codex_usage.total_tokens == 100

    claude_usage = extract_agent_usage(
        stdout='{"type":"result","total_cost_usd":0.01,"usage":{"input_tokens":10,"output_tokens":5}}',
        stderr="",
        command=["claude", "-p", "hi"],
    )
    assert claude_usage is not None
    assert claude_usage.total_cost_usd == 0.01
