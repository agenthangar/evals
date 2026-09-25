# Contributing

Issues and pull requests are welcome for harnesses, task validation, grading,
statistics, reporting, and documentation.

Install the development dependencies and run:

```sh
python -m pytest
bench --tasks examples/tasks validate
bench --tasks examples/tasks smoke
bench --tasks examples/tasks --configs examples/configs/script.yaml --runs /tmp/bench-demo compare --snapshot demo
```

Keep the primary journey short: `init` → `add` → `setup` → `compare`. The MVP
handles Git-based coding tasks with executable checks. Changes to that flow
should include a deterministic end-to-end test with fictional work, actionable
errors, and a comparison whose failures can be inspected. Keep advanced
evaluation options out of the guided path unless they are necessary to finish it.

Use synthetic repositories and data in tests and examples. Never contribute a
real transcript, private task, held-out test, known-good solution, account
configuration, or machine-specific path.

Discovery features must retain scan bounds, exclusions and uncertainty. Test
false links and missed-evidence handling as well as successful retrieval. Do not
turn file counts, repair keywords or transcript retries into a hardness score.
Changes to pilot diagnostics must distinguish execution/grader problems from
completed behavioral failures. Follow [the discovery workflow](docs/DISCOVERY.md).
