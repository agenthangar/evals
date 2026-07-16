import pytest

from bench import harness
from bench.config import ProductConfig
from bench.harness.base import HarnessResult


def test_registry():
    for name in ("claude-code", "codex", "cursor", "script"):
        assert harness.get(name).name in (name, "script")
    with pytest.raises(harness.HarnessError, match="unknown harness"):
        harness.get("copilot")


def test_claude_code_command():
    cfg = ProductConfig(id="c", harness="claude-code", model="model-a",
                        extra_args=["--max-turns", "50"])
    cmd = harness.get("claude-code").command(cfg, "do the thing")
    assert cmd[0] == "claude"
    assert "-p" in cmd and "do the thing" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert cmd[cmd.index("--model") + 1] == "model-a"
    assert cmd[-2:] == ["--max-turns", "50"]


def test_claude_code_usage_parsing():
    result = HarnessResult(
        exit_code=0,
        stdout='{"total_cost_usd": 0.42, "usage": {"input_tokens": 100, '
        '"cache_read_input_tokens": 900, "output_tokens": 50}}',
        stderr="",
        duration_seconds=1.0,
    )
    harness.get("claude-code").parse_usage(result)
    assert result.cost_usd == 0.42
    assert result.input_tokens == 1000
    assert result.output_tokens == 50


def test_claude_code_usage_parsing_garbage():
    result = HarnessResult(exit_code=1, stdout="boom", stderr="", duration_seconds=0.1)
    harness.get("claude-code").parse_usage(result)
    assert result.cost_usd is None


def test_codex_command_and_usage():
    cfg = ProductConfig(id="c", harness="codex", model="model-b")
    cmd = harness.get("codex").command(cfg, "fix it")
    assert cmd[:2] == ["codex", "exec"]
    assert cmd[-1] == "fix it"
    assert "--model" in cmd
    assert "--json" in cmd

    result = HarnessResult(
        exit_code=0,
        stdout='{"type":"turn.completed","usage":{"input_tokens":1000,'
        '"cached_input_tokens":800,"output_tokens":50}}\n',
        stderr="",
        duration_seconds=1.0,
    )
    harness.get("codex").parse_usage(result)
    assert result.input_tokens == 1000
    assert result.cached_input_tokens == 800
    assert result.output_tokens == 50

    result = HarnessResult(
        exit_code=0, stdout="done\ntokens used: 12,345\n", stderr="", duration_seconds=1.0
    )
    harness.get("codex").parse_usage(result)
    assert result.output_tokens == 12345


def test_cursor_command():
    cfg = ProductConfig(id="c", harness="cursor", model=None)
    cmd = harness.get("cursor").command(cfg, "fix it")
    assert cmd[0] == "cursor-agent"
    assert "--force" in cmd and "--model" not in cmd
