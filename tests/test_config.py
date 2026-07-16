from pathlib import Path

import pytest
import yaml

from bench.config import CostModel, ConfigError, load


def write(tmp_path, data):
    p = tmp_path / "products.yaml"
    p.write_text(yaml.safe_dump(data))
    return p


def test_load_valid(tmp_path):
    cfg = load(
        write(
            tmp_path,
            {
                "incumbent": "a",
                "configs": [
                    {"id": "a", "harness": "claude-code", "model": "model-a"},
                    {
                        "id": "b",
                        "harness": "codex",
                        "cost": {"mode": "per_token", "input_per_mtok": 1, "output_per_mtok": 5},
                    },
                ],
            },
        )
    )
    assert cfg.incumbent == "a"
    assert cfg.by_id("b").harness == "codex"


def test_default_incumbent_is_first(tmp_path):
    cfg = load(write(tmp_path, {"configs": [{"id": "x", "harness": "cursor"}]}))
    assert cfg.incumbent == "x"


def test_public_example_loads_concrete_product_matrix():
    path = Path(__file__).parents[1] / "configs" / "products.example.yaml"
    cfg = load(path)

    assert cfg.incumbent == "claude-code-opus"
    assert len(cfg.configs) == 11
    assert cfg.by_id("claude-code-fable").model == "claude-fable-5"
    assert cfg.by_id("codex-sol").model == "gpt-5.6-sol"
    assert cfg.by_id("codex-sol").cost.cached_input_per_mtok == 0.5
    assert cfg.by_id("cursor-default").cost.flat_usd == 0.5
    assert cfg.by_id("cursor-composer-2-5").model == "composer-2.5"
    assert cfg.by_id("cursor-composer-2-5").cost.output_per_mtok == 2.5
    assert cfg.by_id("cursor-grok-4-5").model == "cursor-grok-4.5-high"
    assert cfg.by_id("cursor-grok-4-5").cost.cached_input_per_mtok == 0.5
    assert cfg.by_id("cursor-glm-5-2").model == "glm-5.2-high"
    assert cfg.by_id("cursor-glm-5-2").cost.input_per_mtok == 1.4


def test_duplicate_ids_rejected(tmp_path):
    with pytest.raises(ConfigError, match="duplicate"):
        load(
            write(
                tmp_path,
                {"configs": [{"id": "a", "harness": "codex"}, {"id": "a", "harness": "cursor"}]},
            )
        )


def test_unknown_incumbent_rejected(tmp_path):
    with pytest.raises(ConfigError, match="incumbent"):
        load(write(tmp_path, {"incumbent": "nope", "configs": [{"id": "a", "harness": "codex"}]}))


def test_bad_cost_mode_rejected(tmp_path):
    with pytest.raises(ConfigError, match="cost.mode"):
        load(
            write(
                tmp_path,
                {"configs": [{"id": "a", "harness": "codex", "cost": {"mode": "vibes"}}]},
            )
        )


def test_cost_model_precedence():
    m = CostModel(mode="harness_reported", input_per_mtok=5.0, output_per_mtok=25.0, flat_usd=9.0)
    assert m.cost_usd(1.23, 1_000_000, 1_000_000) == 1.23  # harness wins
    assert m.cost_usd(None, 1_000_000, 1_000_000) == 30.0  # falls back to tokens
    assert m.cost_usd(None, None, None) == 9.0  # falls back to flat

    per_token = CostModel(mode="per_token", input_per_mtok=1.0, output_per_mtok=5.0)
    assert per_token.cost_usd(99.0, 2_000_000, 1_000_000) == 7.0  # ignores harness figure

    cached = CostModel(
        mode="per_token",
        input_per_mtok=5.0,
        cached_input_per_mtok=0.5,
        output_per_mtok=30.0,
    )
    assert cached.cost_usd(None, 1_000_000, 100_000, 800_000) == 4.4

    flat = CostModel(mode="flat_per_run", flat_usd=0.5)
    assert flat.cost_usd(99.0, 1, 1) == 0.5

    assert CostModel(mode="per_token").cost_usd(None, 10, 10) is None
