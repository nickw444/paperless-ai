"""Tests for agent usage metadata extraction."""

from llm.usage import AgentUsageMetadata, extract_usage


def test_extract_usage_from_stderr():
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

    usage = extract_usage(stderr, ["codex", "exec", "--model", "gpt-5.4-mini"])

    assert usage.provider == "openai"
    assert usage.model == "gpt-5.4-mini"
    assert usage.session_id == "abc-123"
    assert usage.total_tokens == 13421
    assert usage.reasoning_effort == "low"
    assert usage.total_cost_usd is None
    assert usage.extra["workdir"] == "/tmp/project"


def test_extract_usage_returns_metadata_with_tokens():
    usage = extract_usage(
        "--------\nmodel: gpt-5\nprovider: openai\n--------\ntokens used\n100\n",
        ["codex", "exec"],
    )
    assert isinstance(usage, AgentUsageMetadata)
    assert usage.total_tokens == 100
