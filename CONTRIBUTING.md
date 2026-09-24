# Contributing

Issues and pull requests are welcome for harnesses, task validation, grading,
statistics, reporting, and documentation.

Install the development dependencies and run:

```sh
python -m pytest
bench --tasks examples/tasks validate
bench --tasks examples/tasks smoke
```

Use synthetic repositories and data in tests and examples. Never contribute a
real transcript, private task, held-out test, known-good solution, account
configuration, or machine-specific path.

Discovery features must retain scan bounds, exclusions and uncertainty. Test
false links and missed-evidence handling as well as successful retrieval. Do not
turn file counts, repair keywords or transcript retries into a hardness score.
Changes to pilot diagnostics must distinguish execution/grader problems from
completed behavioral failures. Follow [the discovery workflow](docs/DISCOVERY.md).
