"""CLI-level test of the full lifecycle against the fixture task."""

from __future__ import annotations

import pytest
import yaml

from bench import __version__
from bench.cli import main
from tests.test_pipeline_e2e import GOOD_PATCH, write_config


def test_cli_lifecycle(task_dir, tmp_path, capsys):
    tasks_dir = str(task_dir.parent)
    good_patch = tmp_path / "good.patch"
    good_patch.write_text(GOOD_PATCH)
    configs = str(write_config(tmp_path / "configs.yaml", good_patch))
    runs = str(tmp_path / "runs")
    base = ["--tasks", tasks_dir, "--configs", configs, "--runs", runs]

    assert main([*base, "validate"]) == 0
    assert "fix-add" in capsys.readouterr().out

    assert main([*base, "smoke"]) == 0
    assert "smoke gate" in capsys.readouterr().out

    assert main([*base, "run", "--snapshot", "snap", "--trials", "1"]) == 0
    capsys.readouterr()

    assert main([*base, "report", "--snapshot", "snap"]) == 0
    out = capsys.readouterr().out
    assert "Routing policy" in out
    routing = yaml.safe_load((tmp_path / "runs" / "snap" / "routing.yaml").read_text())
    assert routing["routing"]["bugfix"]["use"] in ("good-agent", "lazy-agent")


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"bench {__version__}"


def test_cli_doctor_checks_selected_matrix(task_dir, tmp_path, capsys):
    good_patch = tmp_path / "good.patch"
    good_patch.write_text(GOOD_PATCH)
    configs = write_config(tmp_path / "configs.yaml", good_patch)

    assert main(
        [
            "--tasks",
            str(task_dir.parent),
            "--configs",
            str(configs),
            "doctor",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "ready to run" in output
    assert "Python" in output
    assert "tasks: 1 selected" in output


def test_cli_unknown_task_fails_cleanly(task_dir, capsys):
    assert main(
        ["--tasks", str(task_dir.parent), "smoke", "--task", "does-not-exist"]
    ) == 1
    error = capsys.readouterr().err
    assert "ERROR: unknown task id" in error
    assert "fix-add" in error


def test_cli_unknown_config_fails_cleanly(task_dir, tmp_path, capsys):
    good_patch = tmp_path / "good.patch"
    good_patch.write_text(GOOD_PATCH)
    configs = write_config(tmp_path / "configs.yaml", good_patch)

    assert main(
        [
            "--tasks",
            str(task_dir.parent),
            "--configs",
            str(configs),
            "run",
            "--snapshot",
            "snap",
            "--config",
            "does-not-exist",
        ]
    ) == 1
    error = capsys.readouterr().err
    assert "ERROR: unknown config id" in error
    assert "good-agent" in error


def test_cli_missing_config_fails_without_traceback(tmp_path, capsys):
    missing = tmp_path / "missing.yaml"
    assert main(
        ["--configs", str(missing), "report", "--snapshot", "snap"]
    ) == 1
    error = capsys.readouterr().err
    assert "ERROR: config file not found" in error
    assert "Traceback" not in error


def test_cli_rejects_non_positive_run_values():
    with pytest.raises(SystemExit) as exc:
        main(["run", "--snapshot", "snap", "--trials", "0"])
    assert exc.value.code == 2


def test_cli_validate_fails_on_broken_task(task_dir, capsys):
    (task_dir / "prompt.md").write_text("TODO: rewrite this as a real task description\n")
    assert main(["--tasks", str(task_dir.parent), "validate"]) == 1
    assert "INVALID" in capsys.readouterr().err


def test_cli_run_blocks_on_smoke_failure(task_dir, tmp_path, capsys):
    # Make the held-out tests vacuous -> the empty diff passes -> gate failure.
    (task_dir / "tests.patch").write_text(
        "diff --git a/tests/test_calc.py b/tests/test_calc.py\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/tests/test_calc.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def test_add():\n"
        "+    assert True\n"
    )
    good_patch = tmp_path / "good.patch"
    good_patch.write_text(GOOD_PATCH)
    configs = str(write_config(tmp_path / "configs.yaml", good_patch))
    rc = main(
        [
            "--tasks", str(task_dir.parent),
            "--configs", configs,
            "--runs", str(tmp_path / "runs"),
            "run", "--snapshot", "snap",
        ]
    )
    assert rc == 1
    assert "refusing to run" in capsys.readouterr().err
