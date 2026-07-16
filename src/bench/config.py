"""Product/model configurations and their cost models.

A "config" is one thing you might route work to: a product (harness) plus a
model. Copy ``configs/products.example.yaml`` to the gitignored
``configs/products.yaml`` and adjust the concrete example for one benchmark
snapshot::

    incumbent: claude-code-opus        # config id used as the comparison baseline
    configs:
      - id: claude-code-opus
        harness: claude-code          # claude-code | codex | cursor | script
        model: claude-opus-4-8         # passed to the harness's --model flag
        extra_args: []                # appended to the CLI invocation verbatim
        cost:
          mode: harness_reported      # harness_reported | per_token | flat_per_run
          input_per_mtok: 5.0         # used by per_token (and as fallback for
          cached_input_per_mtok: 0.5  #   cached input, when reported
          output_per_mtok: 25.0       #   harness_reported when no cost surfaced)
          flat_usd: 0.50              # used by flat_per_run
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


COST_MODES = ("harness_reported", "per_token", "flat_per_run")


@dataclasses.dataclass
class CostModel:
    mode: str = "harness_reported"
    input_per_mtok: float | None = None
    cached_input_per_mtok: float | None = None
    output_per_mtok: float | None = None
    flat_usd: float | None = None

    def cost_usd(
        self,
        harness_cost_usd: float | None,
        input_tokens: int | None,
        output_tokens: int | None,
        cached_input_tokens: int | None = None,
    ) -> float | None:
        """Best-effort cost of one run; None when nothing can be computed."""
        per_token = None
        if (
            input_tokens is not None
            and output_tokens is not None
            and self.input_per_mtok is not None
            and self.output_per_mtok is not None
        ):
            cached = cached_input_tokens or 0
            uncached = input_tokens - cached
            cached_rate = (
                self.cached_input_per_mtok
                if self.cached_input_per_mtok is not None
                else self.input_per_mtok
            )
            per_token = (
                uncached * self.input_per_mtok
                + cached * cached_rate
                + output_tokens * self.output_per_mtok
            ) / 1_000_000
        if self.mode == "harness_reported":
            if harness_cost_usd is not None:
                return harness_cost_usd
            return per_token if per_token is not None else self.flat_usd
        if self.mode == "per_token":
            return per_token if per_token is not None else self.flat_usd
        return self.flat_usd


@dataclasses.dataclass
class ProductConfig:
    id: str
    harness: str
    model: str | None = None
    extra_args: list[str] = dataclasses.field(default_factory=list)
    cost: CostModel = dataclasses.field(default_factory=CostModel)
    # script harness only: patch file applied instead of running an agent
    patch_file: str | None = None


@dataclasses.dataclass
class BenchConfig:
    incumbent: str
    configs: list[ProductConfig]

    def by_id(self, config_id: str) -> ProductConfig:
        for c in self.configs:
            if c.id == config_id:
                return c
        raise ConfigError(f"unknown config id: {config_id}")


def load(path: Path) -> BenchConfig:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"{path}: invalid YAML: {e}") from e
    if not isinstance(raw, dict) or not isinstance(raw.get("configs"), list):
        raise ConfigError(f"{path}: expected a mapping with a 'configs' list")

    configs = []
    for i, entry in enumerate(raw["configs"]):
        if not isinstance(entry, dict):
            raise ConfigError(f"{path}: configs[{i}] must be a mapping")
        for key in ("id", "harness"):
            if not entry.get(key):
                raise ConfigError(f"{path}: configs[{i}] missing {key!r}")
        cost_raw = entry.get("cost") or {}
        mode = cost_raw.get("mode", "harness_reported")
        if mode not in COST_MODES:
            raise ConfigError(
                f"{path}: configs[{i}].cost.mode must be one of {COST_MODES}, got {mode!r}"
            )
        configs.append(
            ProductConfig(
                id=str(entry["id"]),
                harness=str(entry["harness"]),
                model=entry.get("model"),
                extra_args=[str(a) for a in (entry.get("extra_args") or [])],
                cost=CostModel(
                    mode=mode,
                    input_per_mtok=cost_raw.get("input_per_mtok"),
                    cached_input_per_mtok=cost_raw.get("cached_input_per_mtok"),
                    output_per_mtok=cost_raw.get("output_per_mtok"),
                    flat_usd=cost_raw.get("flat_usd"),
                ),
                patch_file=entry.get("patch_file"),
            )
        )

    ids = [c.id for c in configs]
    if len(set(ids)) != len(ids):
        raise ConfigError(f"{path}: duplicate config ids")

    incumbent = raw.get("incumbent") or ids[0]
    if incumbent not in ids:
        raise ConfigError(f"{path}: incumbent {incumbent!r} is not a defined config id")
    return BenchConfig(incumbent=incumbent, configs=configs)
