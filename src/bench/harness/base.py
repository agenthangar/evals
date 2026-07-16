from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

from bench.config import ProductConfig


class HarnessError(Exception):
    pass


@dataclasses.dataclass
class HarnessResult:
    """Outcome of one agent run, before grading."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    # Cost/usage as reported by the harness itself, when available.
    cost_usd: float | None = None
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None


class Harness:
    """One product's CLI, driven headlessly.

    Adapters build the command line; ``run`` executes it with the workspace
    as the working directory and captures output. Product CLIs change their
    flags over time - per-config ``extra_args`` is the escape hatch, and the
    smoke/validate flow should be re-run whenever a product updates.
    """

    name: str = "base"

    def command(self, config: ProductConfig, prompt: str) -> list[str]:
        raise NotImplementedError

    def run(
        self, config: ProductConfig, workdir: Path, prompt: str, timeout: int
    ) -> HarnessResult:
        import time

        cmd = self.command(config, prompt)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            result = HarnessResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_seconds=time.monotonic() - start,
            )
        except subprocess.TimeoutExpired as e:
            return HarnessResult(
                exit_code=-1,
                stdout=(e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=(e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or ""),
                duration_seconds=time.monotonic() - start,
                timed_out=True,
            )
        except FileNotFoundError:
            raise HarnessError(
                f"{self.name}: CLI {cmd[0]!r} not found on PATH - is the product installed?"
            ) from None
        self.parse_usage(result)
        return result

    def parse_usage(self, result: HarnessResult) -> None:
        """Extract cost/token usage from output, when the product reports it."""
