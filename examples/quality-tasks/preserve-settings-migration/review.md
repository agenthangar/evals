# Grader review

- Explicit opt-outs and missing defaults survive the schema upgrade → `migration`.
- Idempotence, nested isolation, unknown fields and future-version rejection → `preservation`.

Negative controls are complete candidate diffs against the starting tree.
- `false-as-missing`: Treats an explicit opt-out as a missing value.
- `shallow-copy`: Shares nested mutable values with the caller.

Limitations:
- Public teaching fixture with visible reference answers; not a leaderboard task.
- Does not test real storage, SDK initialization or consent UI.
