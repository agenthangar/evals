"""Survey agent-session transcripts to learn your task distribution.

This does NOT try to convert transcripts into benchmark tasks (they aren't
reproducible or gradeable). It answers one question: what kinds of work do
you actually delegate, and in what proportions - so the task suite's category
mix can match reality.

Supported input: a directory tree of JSONL session files (Claude Code stores
these under ~/.claude/projects/<project>/<session>.jsonl; Codex CLI uses a
similar layout under ~/.codex/sessions). Parsing is defensive - unknown lines
are skipped, and the first user-authored text in each file is treated as the
session's task statement.
"""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from pathlib import Path

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bugfix": ("fix", "bug", "broken", "error", "crash", "fail", "regression", "issue"),
    "feature": ("add", "implement", "create", "build", "support", "new "),
    "refactor": ("refactor", "clean up", "cleanup", "rename", "restructure", "simplify", "migrate"),
    "test": ("test", "coverage", "unit test", "spec"),
    "docs": ("readme", "document", "docs", "comment", "changelog"),
    "explain": ("explain", "what does", "how does", "why", "understand", "walk me through"),
    "devops": ("deploy", "docker", "ci", "pipeline", "config", "setup", "install"),
}


def classify(text: str) -> str:
    """Keyword-vote a task statement into a category ('other' when unclear)."""
    lowered = text.lower()
    scores = {
        cat: sum(1 for kw in kws if kw in lowered) for cat, kws in CATEGORY_KEYWORDS.items()
    }
    best = max(scores, key=lambda c: (scores[c], -list(CATEGORY_KEYWORDS).index(c)))
    return best if scores[best] > 0 else "other"


def _extract_text(content) -> str:
    """Message content can be a string or a list of typed blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    return ""


def first_user_message(jsonl_path: Path) -> str | None:
    """First human-authored text in a session transcript, if any."""
    try:
        lines = jsonl_path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        # Claude Code shape: {"type": "user", "message": {"role": "user", "content": ...}}
        # Generic shape:     {"role": "user", "content": ...}
        message = record.get("message") if isinstance(record.get("message"), dict) else record
        if message.get("role") != "user":
            continue
        text = _extract_text(message.get("content")).strip()
        # Skip tool results and harness-injected reminders.
        if not text or text.startswith("<") or "tool_result" in str(message.get("content"))[:200]:
            continue
        return text
    return None


@dataclasses.dataclass
class Survey:
    sessions: int
    categorized: Counter
    examples: dict[str, list[str]]

    def render(self) -> str:
        lines = [
            f"Surveyed {self.sessions} sessions with a usable task statement.",
            "",
            "Category distribution (this is what your task suite should cover):",
        ]
        total = sum(self.categorized.values()) or 1
        for cat, count in self.categorized.most_common():
            lines.append(f"  {cat:<10} {count:>4}  ({count / total:.0%})")
        lines.append("")
        for cat, samples in self.examples.items():
            lines.append(f"[{cat}] e.g. {samples[0][:120]!r}")
        return "\n".join(lines)


def survey(transcripts_dir: Path, max_examples: int = 1) -> Survey:
    transcripts_dir = Path(transcripts_dir).expanduser()
    categorized: Counter = Counter()
    examples: dict[str, list[str]] = {}
    sessions = 0
    for jsonl_path in sorted(transcripts_dir.rglob("*.jsonl")):
        text = first_user_message(jsonl_path)
        if not text:
            continue
        sessions += 1
        category = classify(text)
        categorized[category] += 1
        examples.setdefault(category, [])
        if len(examples[category]) < max_examples:
            examples[category].append(text)
    return Survey(sessions=sessions, categorized=categorized, examples=examples)
