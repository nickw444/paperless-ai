"""Tests for non-interactive apply confirmation."""

from click.testing import CliRunner

from main import _confirm_or_yes, cli


def test_analyze_exposes_yes_flag():
    result = CliRunner().invoke(cli, ["analyze", "--help"])

    assert result.exit_code == 0
    assert "-y, --yes" in result.output
    assert "Automatically confirm apply-time prompts" in result.output


def test_confirm_or_yes_skips_prompt_when_yes_is_set():
    prompts: list[str] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return False

    assert _confirm_or_yes("Apply changes?", yes=True, confirm=confirm) is True
    assert prompts == []


def test_confirm_or_yes_uses_prompt_without_yes():
    prompts: list[str] = []

    def confirm(prompt: str) -> bool:
        prompts.append(prompt)
        return True

    assert _confirm_or_yes("Apply changes?", yes=False, confirm=confirm) is True
    assert prompts == ["Apply changes?"]
