"""Claude Code headless adapter (`claude -p`).

Runs Claude Code non-interactively with permissions disabled and JSON output,
which carries `total_cost_usd` and token usage.
"""

from __future__ import annotations

import json

from bench.config import ProductConfig
from bench.harness.base import Harness, HarnessResult


class ClaudeCodeHarness(Harness):
    name = "claude-code"

    def command(self, config: ProductConfig, prompt: str) -> list[str]:
        cmd = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
        ]
        if config.model:
            cmd += ["--model", config.model]
        cmd += config.extra_args
        return cmd

    def parse_usage(self, result: HarnessResult) -> None:
        try:
            payload = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        cost = payload.get("total_cost_usd")
        if isinstance(cost, (int, float)):
            result.cost_usd = float(cost)
        usage = payload.get("usage")
        if isinstance(usage, dict):
            inp = usage.get("input_tokens")
            out = usage.get("output_tokens")
            if isinstance(inp, int):
                # Count cached reads/writes toward input for a rough total.
                for key in ("cache_read_input_tokens", "cache_creation_input_tokens"):
                    extra = usage.get(key)
                    if isinstance(extra, int):
                        inp += extra
                result.input_tokens = inp
            if isinstance(out, int):
                result.output_tokens = out
