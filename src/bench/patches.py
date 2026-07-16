"""Helpers for working with unified diffs produced by git."""

from __future__ import annotations

import re

_DIFF_HEADER = re.compile(r"^diff --git a/(.*?) b/(.*)$")


def affected_paths(patch_text: str) -> set[str]:
    """Paths touched by a git-format patch (both old and new sides, for renames)."""
    paths: set[str] = set()
    for line in patch_text.splitlines():
        m = _DIFF_HEADER.match(line)
        if m:
            paths.add(m.group(1))
            paths.add(m.group(2))
    return paths


def split_by_paths(patch_text: str, predicate) -> tuple[str, str]:
    """Split a git patch into (matching, non_matching) by file path.

    A file section matches when ``predicate`` is true for either its old or
    new path. Sections are the chunks starting at each ``diff --git`` line.
    """
    matching: list[str] = []
    non_matching: list[str] = []
    current: list[str] | None = None
    current_bucket: list[str] | None = None
    for line in patch_text.splitlines(keepends=True):
        m = _DIFF_HEADER.match(line.rstrip("\n"))
        if m:
            if current is not None:
                current_bucket.extend(current)
            current = [line]
            is_match = predicate(m.group(1)) or predicate(m.group(2))
            current_bucket = matching if is_match else non_matching
        elif current is not None:
            current.append(line)
        # lines before the first diff header (shouldn't exist in git patches) are dropped
    if current is not None:
        current_bucket.extend(current)
    return "".join(matching), "".join(non_matching)


_TEST_PATH = re.compile(
    r"(^|/)(tests?|spec|specs|__tests__)(/|$)"
    r"|(^|/)(test_[^/]+|[^/]+_test\.[^/]+|[^/]+\.test\.[^/]+|[^/]+\.spec\.[^/]+)$"
    r"|(^|/)conftest\.py$",
    re.IGNORECASE,
)

# Xcode commonly puts tests in target-named directories such as
# ``SampleClientTests`` and ``SampleAppUITests`` rather than a bare ``Tests``
# directory. Keep this check case-sensitive so ordinary lowercase names such
# as ``protests`` are not mistaken for test targets.
_XCODE_TEST_PATH = re.compile(r"(^|/)[^/]+Tests(?:/|\.[^/]+$)")


def is_test_path(path: str) -> bool:
    """Heuristic: does this repo path look like test code?"""
    return bool(_TEST_PATH.search(path) or _XCODE_TEST_PATH.search(path))
