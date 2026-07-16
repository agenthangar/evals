"""Cursor CLI headless adapter (`cursor-agent`).

Runs the Cursor agent in print mode with confirmations disabled. Cursor does
not report per-run USD cost in a stable machine-readable way; configure a
per_token or flat_per_run cost model on Cursor configs.
"""

from __future__ import annotations

from bench.config import ProductConfig
from bench.harness.base import Harness


class CursorHarness(Harness):
    name = "cursor"

    def command(self, config: ProductConfig, prompt: str) -> list[str]:
        cmd = [
            "cursor-agent",
            "-p",
            prompt,
            "--force",
            "--output-format",
            "text",
        ]
        if config.model:
            cmd += ["--model", config.model]
        cmd += config.extra_args
        return cmd
