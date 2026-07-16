"""Mining: turn your work history into benchmark inputs.

- ``git_history``: find commits that fixed something *and* changed tests, and
  scaffold them into task directories (SWE-bench style, personal scale).
- ``transcripts``: survey agent-session transcripts (Claude Code JSONL, etc.)
  to learn your task-category distribution - i.e. what the benchmark must
  cover. Transcripts are a survey source only; tasks come from git history.
"""
