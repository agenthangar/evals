"""Deterministic pseudo-harness: applies a fixed patch instead of running an agent.

Used by the test suite and available for pipeline debugging: a config with
``harness: script`` and a ``patch_file`` (absolute path, or relative to the
current working directory) exercises the whole run/grade/report pipeline with
a known outcome.
An empty or missing patch_file yields a no-op agent.
"""

from __future__ import annotations

import time
from pathlib import Path

from bench.config import ProductConfig
from bench.harness.base import Harness, HarnessError, HarnessResult
from bench import workspace


class ScriptHarness(Harness):
    name = "script"

    def run(
        self, config: ProductConfig, workdir: Path, prompt: str, timeout: int
    ) -> HarnessResult:
        start = time.monotonic()
        if config.patch_file:
            patch_path = Path(config.patch_file)
            if not patch_path.is_file():
                raise HarnessError(f"script harness: patch file not found: {patch_path}")
            workspace.apply_patch(workdir, patch_path.read_text())
        return HarnessResult(
            exit_code=0,
            stdout=f"script harness applied {config.patch_file or 'no patch'}",
            stderr="",
            duration_seconds=time.monotonic() - start,
            cost_usd=0.0,
            input_tokens=0,
            output_tokens=0,
        )
