"""Survey agent-session transcripts to learn your task distribution.

This does NOT try to convert transcripts into benchmark tasks (they aren't
reproducible or gradeable). It answers one question: what kinds of work do
you actually delegate, and in what proportions - so the task suite's category
mix can match reality.

Supported inputs are directory trees of Claude Code or Codex JSONL sessions.
Parsing is defensive: malformed and unknown records are skipped, injected
context is excluded, and every main-thread user/assistant message is retained
in a source-neutral session model. The survey uses the first real user message
as the session's task statement.
"""

from __future__ import annotations

import dataclasses
import json
import re
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

SOURCES = ("codex", "claude", "generic")
MODES = ("interactive", "automation", "benchmark", "unknown")

_CODEX_REQUEST_MARKER = "## My request for Codex:"
_INJECTED_PREFIXES = (
    "<recommended_plugins>",
    "<environment_context>",
    "<permissions instructions>",
    "<collaboration_mode>",
    "<skills_instructions>",
    "<apps_instructions>",
    "<plugins_instructions>",
    "<system-reminder>",
    "<task-notification>",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<tool_result>",
)
_BENCHMARK_CWD = re.compile(r"(^|/)bench-run-[^/]+(/|$)")


def classify(text: str) -> str:
    """Keyword-vote a task statement into a category ('other' when unclear)."""
    lowered = text.lower()
    scores = {
        cat: sum(1 for kw in kws if kw in lowered) for cat, kws in CATEGORY_KEYWORDS.items()
    }
    best = max(scores, key=lambda c: (scores[c], -list(CATEGORY_KEYWORDS).index(c)))
    return best if scores[best] > 0 else "other"


@dataclasses.dataclass(frozen=True)
class TranscriptMessage:
    role: str
    text: str
    timestamp: str | None = None


@dataclasses.dataclass
class TranscriptSession:
    path: Path
    source: str = "generic"
    session_id: str | None = None
    cwd: str | None = None
    originator: str | None = None
    entrypoint: str | None = None
    transport: str | None = None
    started_at: str | None = None
    messages: list[TranscriptMessage] = dataclasses.field(default_factory=list)
    malformed_lines: int = 0

    @property
    def user_messages(self) -> list[str]:
        return [message.text for message in self.messages if message.role == "user"]

    @property
    def assistant_messages(self) -> list[str]:
        return [message.text for message in self.messages if message.role == "assistant"]

    @property
    def first_user_message(self) -> str | None:
        return next(iter(self.user_messages), None)

    @property
    def mode(self) -> str:
        if self.cwd and _BENCHMARK_CWD.search(self.cwd):
            return "benchmark"
        if self.source == "codex":
            originator = (self.originator or "").lower()
            if originator == "codex desktop":
                return "interactive"
            if originator == "codex_exec" or (
                not originator and (self.transport or "").lower() == "exec"
            ):
                return "automation"
        if self.source == "claude":
            entrypoint = (self.entrypoint or "").lower()
            if entrypoint in ("cli", "claude-desktop"):
                return "interactive"
            if entrypoint.startswith("sdk"):
                return "automation"
        return "unknown"


def _extract_text(content, allowed_types: tuple[str, ...]) -> str:
    """Extract visible message text from string or typed-block content."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") not in allowed_types:
            continue
        text = block.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def _clean_user_text(text: str) -> str:
    """Remove known harness/UI context while preserving the actual request."""
    text = text.strip()
    if not text:
        return ""
    marker_at = text.find(_CODEX_REQUEST_MARKER)
    wrapper_prefix = text[:marker_at].lower() if marker_at >= 0 else ""
    is_wrapped_request = marker_at == 0 or (
        marker_at > 0
        and (
            text.lower().startswith("# files mentioned by the user:")
            or "<in-app-browser-context" in wrapper_prefix
        )
    )
    if is_wrapped_request:
        text = text.rsplit(_CODEX_REQUEST_MARKER, 1)[1].strip()
    lowered = text.lower()
    if any(lowered.startswith(prefix.lower()) for prefix in _INJECTED_PREFIXES):
        return ""
    # An attachment-only block is context, not a task. Wrapped attachment
    # requests were already reduced to the text after the marker above.
    if lowered.startswith("# files mentioned by the user:"):
        return ""
    return text


def _extract_user_text(content, allowed_types: tuple[str, ...]) -> str:
    """Clean each user block separately so injected siblings do not hide a request."""
    if isinstance(content, str):
        return _clean_user_text(content)
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") not in allowed_types:
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        cleaned = _clean_user_text(text)
        if cleaned:
            parts.append(cleaned)
    return "\n".join(parts)


def _message_timestamp(record: dict) -> str | None:
    timestamp = record.get("timestamp")
    return timestamp if isinstance(timestamp, str) else None


def _set_first(current: str | None, candidate) -> str | None:
    return current or (candidate if isinstance(candidate, str) and candidate else None)


def _parse_codex_record(session: TranscriptSession, record: dict) -> None:
    record_type = record.get("type")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return
    if record_type == "session_meta":
        session.source = "codex"
        session.session_id = _set_first(
            session.session_id, payload.get("id") or payload.get("session_id")
        )
        session.cwd = _set_first(session.cwd, payload.get("cwd"))
        session.originator = _set_first(session.originator, payload.get("originator"))
        session.transport = _set_first(session.transport, payload.get("source"))
        session.started_at = _set_first(session.started_at, payload.get("timestamp"))
        return
    if record_type != "response_item" or payload.get("type") != "message":
        return
    session.source = "codex"
    timestamp = _message_timestamp(record)
    session.started_at = _set_first(session.started_at, timestamp)
    role = payload.get("role")
    if role == "user":
        text = _extract_user_text(payload.get("content"), ("input_text",))
    elif role == "assistant":
        text = _extract_text(payload.get("content"), ("output_text",)).strip()
    else:
        return
    if text:
        session.messages.append(TranscriptMessage(role=role, text=text, timestamp=timestamp))


def _parse_claude_record(session: TranscriptSession, record: dict) -> None:
    if record.get("type") not in ("user", "assistant"):
        return
    message = record.get("message")
    if not isinstance(message, dict):
        return
    session.source = "claude"
    session.session_id = _set_first(session.session_id, record.get("sessionId"))
    session.cwd = _set_first(session.cwd, record.get("cwd"))
    session.entrypoint = _set_first(session.entrypoint, record.get("entrypoint"))
    session.started_at = _set_first(session.started_at, record.get("timestamp"))
    if record.get("isSidechain") is True:
        return
    role = message.get("role")
    if role == "user":
        text = _extract_user_text(message.get("content"), ("text", "input_text"))
    elif role == "assistant":
        text = _extract_text(message.get("content"), ("text", "output_text")).strip()
    else:
        return
    if text:
        session.messages.append(
            TranscriptMessage(role=role, text=text, timestamp=_message_timestamp(record))
        )


def _parse_generic_record(session: TranscriptSession, record: dict) -> None:
    role = record.get("role")
    if role not in ("user", "assistant"):
        return
    if role == "user":
        text = _extract_user_text(record.get("content"), ("text", "input_text"))
    else:
        text = _extract_text(record.get("content"), ("text", "output_text")).strip()
    if text:
        session.messages.append(
            TranscriptMessage(role=role, text=text, timestamp=_message_timestamp(record))
        )


def parse_session(jsonl_path: Path) -> TranscriptSession:
    """Parse one Codex, Claude Code, or generic JSONL transcript."""
    jsonl_path = Path(jsonl_path)
    session = TranscriptSession(path=jsonl_path)
    try:
        lines = jsonl_path.open(errors="replace")
    except OSError:
        return session
    with lines:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                session.malformed_lines += 1
                continue
            if not isinstance(record, dict):
                continue
            record_type = record.get("type")
            if record_type in ("session_meta", "response_item", "event_msg", "turn_context"):
                _parse_codex_record(session, record)
            elif record_type in ("user", "assistant") and isinstance(record.get("message"), dict):
                _parse_claude_record(session, record)
            else:
                _parse_generic_record(session, record)
    return session


def first_user_message(jsonl_path: Path) -> str | None:
    """First human-authored text in a session transcript, if any."""
    return parse_session(jsonl_path).first_user_message


@dataclasses.dataclass
class Survey:
    sessions: int
    categorized: Counter
    examples: dict[str, list[str]]
    sources: Counter = dataclasses.field(default_factory=Counter)
    modes: Counter = dataclasses.field(default_factory=Counter)

    def render(self) -> str:
        noun = "session" if self.sessions == 1 else "sessions"
        lines = [
            f"Surveyed {self.sessions} {noun} with a usable task statement.",
            "",
        ]
        if self.sources:
            lines.append("Sources:")
            for source, count in self.sources.most_common():
                lines.append(f"  {source:<12} {count:>4}")
            lines.append("")
        if self.modes:
            lines.append("Session modes:")
            for mode, count in self.modes.most_common():
                lines.append(f"  {mode:<12} {count:>4}")
            lines.append("")
        lines.append("Category distribution (this is what your task suite should cover):")
        total = sum(self.categorized.values()) or 1
        for cat, count in self.categorized.most_common():
            lines.append(f"  {cat:<10} {count:>4}  ({count / total:.0%})")
        lines.append("")
        for cat, samples in self.examples.items():
            if samples:
                lines.append(f"[{cat}] e.g. {samples[0][:120]!r}")
        return "\n".join(lines)


def survey(
    transcripts_dir: Path,
    max_examples: int = 1,
    source: str | None = None,
    mode: str | None = None,
) -> Survey:
    transcripts_dir = Path(transcripts_dir).expanduser()
    categorized: Counter = Counter()
    examples: dict[str, list[str]] = {}
    sources: Counter = Counter()
    modes: Counter = Counter()
    sessions = 0
    for jsonl_path in sorted(transcripts_dir.rglob("*.jsonl")):
        session = parse_session(jsonl_path)
        text = session.first_user_message
        if not text:
            continue
        if source is not None and session.source != source:
            continue
        if mode is not None and session.mode != mode:
            continue
        sessions += 1
        sources[session.source] += 1
        modes[session.mode] += 1
        category = classify(text)
        categorized[category] += 1
        examples.setdefault(category, [])
        if len(examples[category]) < max_examples:
            examples[category].append(text)
    return Survey(
        sessions=sessions,
        categorized=categorized,
        examples=examples,
        sources=sources,
        modes=modes,
    )
