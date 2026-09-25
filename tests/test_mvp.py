"""Exercise the new-user journey with real Git checkouts and deterministic agents."""
from __future__ import annotations

import dataclasses
import json
import re
import sys

import pytest
import yaml

from bench import comparison, config, runner
from bench.cli import main
from bench.task import Task, TaskError
from tests.conftest import git


def add_arguments(repo, prompt, *extra):
    return ["add", str(repo["repo"]), repo["fix"], "--id", "sum",
            "--prompt-file", str(prompt), "--test-command",
            f"{sys.executable} -m pytest tests/ -q", *extra]


def test_private_pack_to_comparison_and_saved_report(fixture_repo, tmp_path, monkeypatch, capsys):
    pack = tmp_path / "my benchmark"
    assert main(["init", str(pack)]) == 0
    monkeypatch.chdir(pack)
    prompt = pack / "request.md"
    prompt.write_text("Make add(a, b) return the sum, including negative inputs.\n")
    original_head = git(fixture_repo["repo"], "rev-parse", "HEAD")
    assert main(add_arguments(fixture_repo, prompt, "--must-pass")) == 0
    task = Task.load(pack / "tasks" / "sum")
    assert task.must_pass
    assert task.base_commit == fixture_repo["base"]
    assert git(fixture_repo["repo"], "rev-parse", "HEAD") == original_head
    assert not git(fixture_repo["repo"], "status", "--porcelain")

    # Real setup commands, with no account access or model calls.
    assert main(["setup", "--id", "current", "--harness", "codex", "--model", "model-a",
                 "--cost", "flat", "--flat-price", "1"]) == 0
    assert main(["setup", "--id", "cheap", "--harness", "codex", "--model", "model-b",
                 "--cost", "flat", "--flat-price", "0.2"]) == 0
    cfg_path = pack / "configs" / "products.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    for entry in cfg["configs"]:
        entry["harness"] = "script"
    cfg["configs"][0]["patch_file"] = str(pack / "tasks" / "sum" / "solution.patch")
    cfg_path.write_text(yaml.safe_dump(cfg))
    capsys.readouterr()

    assert main(["compare", "--snapshot", "first", "--trials", "2"]) == 0
    snapshot = pack / "runs" / "first"
    summary = json.loads((snapshot / "comparison.json").read_text())
    assert summary["observed_cost_pick"] == "current"
    cheap = next(r for r in summary["setups"] if r["id"] == "cheap")
    assert cheap["must_pass_failures"] == ["sum"]
    assert cheap["attempts_passed"] == 0
    assert cheap["total_cost_usd"] == 0.4  # Failed attempts still cost money.
    report = (snapshot / "comparison.md").read_text()
    assert "flat estimate" in report
    assert "Median time" in report
    assert "Routing policy" not in report
    for target in re.findall(r"\]\(([^)]+)\)", report):
        assert (snapshot / target).is_file(), target

    result_files = sorted(snapshot.glob("*/*/trial-*/result.json"))
    before = [p.read_bytes() for p in result_files]
    assert main(["compare", "--snapshot", "first", "--trials", "2"]) == 0
    assert [p.read_bytes() for p in result_files] == before

    # Report-only reads frozen must-pass flags; it does not run tests or read tasks.
    monkeypatch.setattr(runner, "run_matrix", lambda *a, **k: pytest.fail("must not run agents"))
    monkeypatch.setattr("bench.cli._load_tasks", lambda *a: pytest.fail("must not load tasks"))
    task_path = pack / "tasks" / "sum" / "task.yaml"
    metadata = yaml.safe_load(task_path.read_text())
    metadata["must_pass"] = False
    task_path.write_text(yaml.safe_dump(metadata))
    assert main(["compare", "--snapshot", "first", "--report-only"]) == 0
    assert json.loads((snapshot / "comparison.json").read_text())["must_pass"] == ["sum"]
    assert [p.read_bytes() for p in result_files] == before


def test_guided_task_and_setup(fixture_repo, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers = iter(["1", "sum", "Return the sum of two numbers.", "",
                    f"{sys.executable} -m pytest tests/ -q", "yes"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    assert main(["add", str(fixture_repo["repo"])]) == 0
    assert Task.load(tmp_path / "tasks" / "sum").must_pass
    answers = iter(["current", "codex", "model-a", '-c model_reasoning_effort="high"',
                    "tokens", "2", "10", "0.2"])
    assert main(["setup"]) == 0
    setup = config.load(tmp_path / "configs" / "products.yaml").configs[0]
    assert setup.cost.cached_input_per_mtok == 0.2
    assert setup.extra_args == ["-c", "model_reasoning_effort=high"]
    assert "Ready: sum" in capsys.readouterr().out


def test_add_supports_separate_tests_for_untested_work(fixture_repo, tmp_path, monkeypatch):
    repo = fixture_repo["repo"]
    patch = git(repo, "show", fixture_repo["fix"], "--format=", "--", "tests/test_calc.py") + "\n"
    tests = tmp_path / "heldout.patch"
    tests.write_text(patch)
    git(repo, "checkout", "--detach", fixture_repo["base"])
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    git(repo, "add", "calc.py")
    git(repo, "commit", "-qm", "repair addition")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Return the sum of the two inputs.\n")
    monkeypatch.chdir(tmp_path)
    fixture_repo = {**fixture_repo, "fix": git(repo, "rev-parse", "HEAD")}
    assert main(add_arguments(fixture_repo, prompt, "--tests-patch", str(tests))) == 0
    assert Task.load(tmp_path / "tasks" / "sum").tests_patch == patch


def test_bad_checks_remain_editable_and_block_comparison(fixture_repo, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Return the sum of the inputs.\n")
    arguments = add_arguments(fixture_repo, prompt)
    arguments[-1] = "true"  # A vacuous grader must not create a ready task.
    assert main(arguments) == 1
    assert "Task needs attention" in capsys.readouterr().out
    assert (tmp_path / "tasks" / "sum" / "task.yaml").is_file()
    cfg = {"configs": [{"id": "one", "harness": "script"}, {"id": "two", "harness": "script"}]}
    cfg_path = tmp_path / "setups.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    monkeypatch.setattr(runner, "run_matrix", lambda *a, **k: pytest.fail("uncalibrated task ran"))
    assert main(["--configs", str(cfg_path), "compare", "--snapshot", "bad"]) == 1
    assert "GATE FAILED" in capsys.readouterr().err


def test_creation_never_overwrites_existing_work(fixture_repo, tmp_path, monkeypatch):
    pack = tmp_path / "pack"
    assert main(["init", str(pack)]) == 0
    original = (pack / "README.md").read_text()
    assert main(["init", str(pack)]) == 1
    assert (pack / "README.md").read_text() == original
    monkeypatch.chdir(pack)
    setup_args = ["setup", "--id", "current", "--harness", "codex", "--model", "model-a"]
    assert main(setup_args) == 0
    cfg_path = pack / "configs" / "products.yaml"
    original = cfg_path.read_bytes()
    assert main(setup_args) == 1
    assert cfg_path.read_bytes() == original
    prompt = pack / "request.md"
    prompt.write_text("Return the sum.\n")
    assert main(add_arguments(fixture_repo, prompt)) == 0
    assert main(add_arguments(fixture_repo, prompt)) == 1


@pytest.mark.parametrize("price", ["-1", "nan", "inf"])
def test_invalid_price_does_not_save_setup(tmp_path, monkeypatch, price):
    monkeypatch.chdir(tmp_path)
    assert main(["setup", "--id", "bad", "--harness", "codex", "--model", "model-a",
                 "--cost", "flat", "--flat-price", price]) == 1
    assert not (tmp_path / "configs" / "products.yaml").exists()


def test_missing_noninteractive_input_has_actionable_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert main(["setup"]) == 1
    assert "provide --id" in capsys.readouterr().err


@pytest.mark.parametrize("make_current", [False, True])
def test_setup_preserves_implicit_baseline_unless_requested(tmp_path, make_current):
    path = tmp_path / "setups.yaml"
    path.write_text(yaml.safe_dump({"configs": [{"id": "existing", "harness": "script"}]}))
    args = ["--configs", str(path), "setup", "--id", "alternative", "--harness", "codex",
            "--model", "model-b"]
    assert main(args + (["--current"] if make_current else [])) == 0
    assert config.load(path).incumbent == ("alternative" if make_current else "existing")


def trial(task, setup, passed=True, cost=1.0, number=1, **extra):
    return runner.TrialResult(task, "coding", setup, number, passed,
                             "tests_passed" if passed else "tests_failed", cost, 10, False, 1,
                             agent_exit_code=0, artifact_passed=passed, cost_source="flat_estimate", **extra)


def setups():
    return config.BenchConfig("current", [config.ProductConfig("current", "script"),
                                          config.ProductConfig("cheap", "script")])


def test_cheapest_eligible_setup_and_different_failures_are_visible():
    results = [trial("a", "current"), trial("b", "current", False),
               trial("a", "cheap", False, .1), trial("b", "cheap", True, .1)]
    summary = comparison.summarize(results, setups(), [])
    assert summary["observed_cost_pick"] == "cheap"
    assert comparison.summarize(results, setups(), ["a"])["observed_cost_pick"] == "current"
    report = comparison.render(summary, results, "pilot")
    assert "a/cheap/trial-1/tests.log" in report
    assert "b/current/trial-1/tests.log" in report


def test_repetition_does_not_hide_must_pass_failure():
    results = [trial("a", "current", number=i) for i in (1, 2)]
    results += [trial("a", "cheap", i == 1, .1, i) for i in (1, 2)]
    summary = comparison.summarize(results, setups(), ["a"])
    cheap = summary["setups"][1]
    assert cheap["tasks_passed"] == 0
    assert cheap["attempts_passed"] == 1
    assert cheap["cost_per_success_usd"] == .2
    assert not cheap["meets_bar"]


@pytest.mark.parametrize("mutation", [
    {"cost_usd": None}, {"cost_source": "unknown"}, {"grade_reason": "environment_error"},
    {"agent_exit_code": None},
])
def test_missing_cost_or_unreviewed_execution_cannot_pick_a_winner(mutation):
    results = [trial("a", "current"), dataclasses.replace(trial("a", "cheap", cost=.1), **mutation)]
    assert comparison.summarize(results, setups(), ["a"])["observed_cost_pick"] is None


def test_later_environment_failure_requires_review_even_if_first_check_failed():
    interrupted_grading = trial("b", "cheap", False, .1, check_results=[
        {"id": "behavior", "passed": False, "reason": "tests_failed"},
        {"id": "integration", "passed": False, "reason": "environment_error"},
    ])
    results = [trial("a", "current"), trial("b", "current", False),
               trial("a", "cheap", cost=.1), interrupted_grading]
    summary = comparison.summarize(results, setups(), [])
    assert summary["observed_cost_pick"] is None
    assert "grading problems" in summary["reason"]


@pytest.mark.parametrize("agent_reason", ["agent_exited_nonzero", "agent_timed_out"])
def test_agent_failure_cannot_hide_grading_problem(agent_reason):
    failed = dataclasses.replace(trial("b", "cheap", False, .1),
                                 grade_reason=agent_reason, agent_exit_code=1,
                                 agent_timed_out=agent_reason == "agent_timed_out",
                                 artifact_grade_reason="patch_apply_failed")
    results = [trial("a", "current"), trial("b", "current", False),
               trial("a", "cheap", cost=.1), failed]
    summary = comparison.summarize(results, setups(), [])
    assert summary["observed_cost_pick"] is None
    assert summary["setups"][1]["needs_review"]
    report = comparison.render(summary, results, "pilot")
    assert agent_reason in report
    assert "artifact: patch_apply_failed" in report


def test_all_failed_has_no_pick_and_unmatched_cells_are_rejected():
    results = [trial("a", "current", False), trial("a", "cheap", False)]
    assert comparison.summarize(results, setups(), [])["observed_cost_pick"] is None
    results.append(trial("b", "cheap"))
    with pytest.raises(runner.RunError, match="same task/trial"):
        comparison.summarize(results, setups(), [])


def test_must_pass_is_validated_and_frozen(task_dir, tmp_path):
    path = task_dir / "task.yaml"
    meta = yaml.safe_load(path.read_text())
    meta["must_pass"] = "yes"
    path.write_text(yaml.safe_dump(meta))
    with pytest.raises(TaskError, match="must_pass"):
        Task.load(task_dir)
    meta["must_pass"] = True
    path.write_text(yaml.safe_dump(meta))
    task = Task.load(task_dir)
    cfg = config.BenchConfig("script", [config.ProductConfig("script", "script")])
    runner.run_matrix([task], cfg, tmp_path / "snapshot", trials=1)
    with pytest.raises(runner.RunError, match="inputs changed"):
        runner.run_matrix([dataclasses.replace(task, must_pass=False)], cfg, tmp_path / "snapshot", trials=1)


def test_grader_crash_preserves_completed_agent_evidence(task_dir, tmp_path, monkeypatch):
    task = Task.load(task_dir)
    cfg = config.ProductConfig("good", "script", patch_file=str(task_dir / "solution.patch"))
    def crash(*args):
        raise OSError("grader unavailable")
    monkeypatch.setattr("bench.runner.grade.grade_diff", crash)
    out = tmp_path / "attempt"
    with pytest.raises(OSError, match="unavailable"):
        runner.run_trial(task, cfg, 1, out)
    assert (out / "diff.patch").read_text() == task.solution_patch
    assert "exit=0" in (out / "agent.log").read_text()
    assert not (out / "result.json").exists()
