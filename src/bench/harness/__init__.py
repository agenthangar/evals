"""Harness adapters: run one config's product CLI against a prepared workspace."""

from __future__ import annotations

from bench.harness.base import Harness, HarnessResult, HarnessError
from bench.harness.claude_code import ClaudeCodeHarness
from bench.harness.codex import CodexHarness
from bench.harness.cursor import CursorHarness
from bench.harness.script import ScriptHarness

_REGISTRY: dict[str, type[Harness]] = {
    "claude-code": ClaudeCodeHarness,
    "codex": CodexHarness,
    "cursor": CursorHarness,
    "script": ScriptHarness,
}


def get(name: str) -> Harness:
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise HarnessError(
            f"unknown harness {name!r}; available: {sorted(_REGISTRY)}"
        ) from None


__all__ = ["Harness", "HarnessResult", "HarnessError", "get"]
