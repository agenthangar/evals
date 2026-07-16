"""OpenAI Codex CLI headless adapter (`codex exec`).

Runs Codex non-interactively with sandbox/approvals disabled. Token usage is
read from ``codex exec --json`` so standard API pricing can distinguish
uncached input, cached input, and output tokens.
"""

from __future__ import annotations

import json
import re

from bench.config import ProductConfig
from bench.harness.base import Harness, HarnessResult

_TOKENS_USED = re.compile(r"tokens?\s+used[:\s]+([\d,]+)", re.IGNORECASE)


class CodexHarness(Harness):
    name = "codex"

    def command(self, config: ProductConfig, prompt: str) -> list[str]:
        cmd = [
            "codex",
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--json",
        ]
        if config.model:
            cmd += ["--model", config.model]
        cmd += config.extra_args
        cmd.append(prompt)
        return cmd

    def parse_usage(self, result: HarnessResult) -> None:
        usage = None
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            candidate = event.get("usage") if isinstance(event, dict) else None
            if isinstance(candidate, dict) and {
                "input_tokens", "output_tokens"
            } <= candidate.keys():
                usage = candidate
        if usage is not None:
            result.input_tokens = int(usage["input_tokens"])
            result.cached_input_tokens = int(usage.get("cached_input_tokens", 0))
            result.output_tokens = int(usage["output_tokens"])
            return

        # Backward compatibility for older Codex versions and saved output.
        m = _TOKENS_USED.search(result.stdout) or _TOKENS_USED.search(result.stderr)
        if m:
            total = int(m.group(1).replace(",", ""))
            # The CLI reports a single total; attribute it to output tokens so
            # a per_token cost model prices it conservatively.
            result.input_tokens = 0
            result.output_tokens = total
