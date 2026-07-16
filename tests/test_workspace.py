import subprocess

from bench.workspace import capture_diff


def git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_capture_diff_tolerates_non_utf8_text(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "bench@localhost")
    git(repo, "config", "user.name", "bench")
    (repo / ".gitattributes").write_text("*.txt diff\n")
    (repo / "output.txt").write_text("before\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")

    (repo / "output.txt").write_bytes(b"after \xa4\n")

    diff = capture_diff(repo, base)
    assert "output.txt" in diff
    assert "after" in diff
    assert "\ufffd" in diff
