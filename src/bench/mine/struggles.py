"""Find user-reported unresolved work, excluding assistant claims and reasoning."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
from pathlib import Path
import re

from bench.mine import transcripts
from bench.mine.git_history import MineError

SIGNALS = {
    'reported_unresolved': re.compile(r"\b(?:still\s+(?:broken|fails?|failing|crash(?:es|ing)?|not\s+working|doesn['’]?t\s+work)|(?:didn['’]?t|doesn['’]?t|did\s+not|does\s+not)\s+(?:work|fix)|not\s+(?:fixed|resolved))\b", re.I),
    'reported_regression': re.compile(r"\b(?:regressed|(?:this|that|it)\s+(?:is|caused)\s+a\s+regression|broke\s+again|broken\s+again|stopped\s+working|used\s+to\s+work)\b", re.I),
    'requested_retry': re.compile(r"\b(?:try\s+again|revert\s+(?:this|that|the\s+change)|undo\s+(?:this|that))\b", re.I),
}


def discover(directory: Path, source: str | None = None, mode: str = 'interactive',
             repo: Path | None = None, since: str | None = None,
             include_excerpts: bool = False) -> dict:
    directory = Path(directory).expanduser().resolve()
    if not directory.is_dir():
        raise MineError(f'transcript directory not found: {directory}')
    if since:
        try:
            cutoff = datetime.fromisoformat(since).date()
        except ValueError as exc:
            raise MineError('--since must be an ISO date, e.g. 2026-09-01') from exc
    else:
        cutoff = None
    repo = Path(repo).expanduser().resolve() if repo else None
    counts = Counter()
    candidates = []
    for path in sorted(directory.rglob('*.jsonl')):
        counts['files_scanned'] += 1
        session = transcripts.parse_session(path)
        if not session.first_user_message:
            counts['without_request'] += 1
            continue
        if source and session.source != source:
            counts['excluded_source'] += 1
            continue
        if session.mode == 'benchmark':
            counts['excluded_benchmark'] += 1
            continue
        if mode != 'all' and session.mode != mode:
            counts['excluded_mode'] += 1
            continue
        if repo and (not session.cwd or not Path(session.cwd).expanduser().resolve().is_relative_to(repo)):
            counts['excluded_repository'] += 1
            continue
        if cutoff:
            try:
                day = datetime.fromisoformat((session.started_at or '').replace('Z', '+00:00')).date()
            except ValueError:
                counts['excluded_unknown_date'] += 1
                continue
            if day < cutoff:
                counts['excluded_date'] += 1
                continue
        counts['eligible_sessions'] += 1
        assistant_seen = False
        seen = set()
        evidence = []
        for index, message in enumerate(session.messages):
            if message.role == 'assistant':
                assistant_seen = True
                continue
            if not assistant_seen:
                continue
            digest = hashlib.sha256(message.text.encode()).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            # A request to check that nothing regressed is not a regression report.
            # This only removes a few explicit negations; source review is still required.
            signal_text = re.sub(r"\b(?:nothing|not|never|hasn['’]?t|haven['’]?t)\s+regressed\b",
                                 '', message.text, flags=re.I)
            matches = [name for name, pattern in SIGNALS.items() if pattern.search(signal_text)]
            if matches:
                entry = {'message_index': index, 'timestamp': message.timestamp,
                         'message_sha256': digest, 'signals': matches}
                if include_excerpts:
                    entry['excerpt'] = message.text[:240]
                evidence.append(entry)
        if not evidence:
            counts['without_signals'] += 1
            continue
        candidate = {'id': 'session-' + hashlib.sha256(str(path.relative_to(directory)).encode()).hexdigest()[:16],
                     'path_relative_to_input': str(path.relative_to(directory)),
                     'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                     'session_id': session.session_id, 'source': session.source,
                     'mode': session.mode, 'cwd': session.cwd, 'started_at': session.started_at,
                     'request_sha256': hashlib.sha256(session.first_user_message.encode()).hexdigest(),
                     'evidence': evidence, 'difficulty': 'unmeasured', 'admission': 'discovery_only'}
        if include_excerpts:
            candidate['request_excerpt'] = session.first_user_message[:240]
        candidates.append(candidate)
    return {'schema': 1, 'privacy': 'local_private_inventory', 'input_directory': str(directory),
            'parameters': {'source': source, 'mode': mode, 'repository': str(repo) if repo else None,
                           'since': since, 'include_excerpts': include_excerpts},
            'counts': dict(counts), 'candidates': candidates,
            'limitations': ['Language heuristics produce both false positives and missed incidents; review the original user turns.',
                            'Retry requests may concern preferences, unavailable tools or permissions rather than model difficulty.',
                            'Only visible user corrections after an assistant message count; no reasoning or tool transcripts are exported.',
                            'Paths, hashes and project metadata are private even when excerpts are disabled.']}
