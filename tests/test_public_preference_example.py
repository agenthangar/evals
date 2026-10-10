from pathlib import Path

import yaml

from bench.cli import main


ROOT = Path(__file__).parents[1]


def test_public_preference_example_runs_complete_blinded_lifecycle(tmp_path, capsys):
    tasks = ROOT / "examples" / "preference-tasks"
    configs = ROOT / "examples" / "configs" / "preference-script.yaml"
    runs = tmp_path / "runs"
    base = [
        "--tasks",
        str(tasks),
        "--configs",
        str(configs),
        "--runs",
        str(runs),
    ]

    assert main([*base, "doctor"]) == 0
    assert "ready to run" in capsys.readouterr().out
    assert main([*base, "validate"]) == 0
    assert "grader=preference" in capsys.readouterr().out
    assert main([*base, "smoke"]) == 0
    capsys.readouterr()
    assert main([*base, "run", "--snapshot", "preference-demo", "--trials", "1"]) == 0
    capsys.readouterr()
    assert main(
        [
            *base,
            "preference",
            "prepare",
            "--snapshot",
            "preference-demo",
            "--config",
            "brief-style-one",
            "--config",
            "brief-style-two",
        ]
    ) == 0
    capsys.readouterr()

    review = (
        runs
        / "preference-demo"
        / "preference-review"
        / "calculator-demo-brief"
        / "trial-1"
    )
    prompt = (review / "prompt.md").read_text()
    rubric = (review / "rubric.md").read_text()
    candidate_a = (review / "candidate-a.md").read_text()
    candidate_b = (review / "candidate-b.md").read_text()
    assert candidate_a != candidate_b
    assert candidate_a.count("\n- ") == 3
    assert candidate_b.count("\n- ") == 3
    visible = "\n".join((prompt, rubric, candidate_a, candidate_b))
    assert "brief-style-one" not in visible
    assert "brief-style-two" not in visible
    assert yaml.safe_load((review / "judgment.yaml").read_text())["winner"] is None

    (review / "judgment.yaml").write_text(
        "winner: tie\n"
        "rationale: Both are credible; CI uses tie only to exercise reporting.\n"
    )
    assert main([*base, "preference", "report", "--snapshot", "preference-demo"]) == 0
    capsys.readouterr()

    report = yaml.safe_load(
        (runs / "preference-demo" / "preference-results.yaml").read_text()
    )
    assert report["pending"] == 0
    assert report["summary"]["brief-style-one"]["ties"] == 1
    assert report["summary"]["brief-style-two"]["ties"] == 1
    assert report["judgments"][0]["winner"] == "tie"
