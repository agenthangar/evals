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
