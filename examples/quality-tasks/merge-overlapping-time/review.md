# Grader review

- Overlaps, nesting, duplicates and ordering match an independent minute-grid oracle → `union`.
- Clipping, negative bounds, empty ranges and input immutability → `contract`.

Negative controls are complete candidate diffs against the starting tree.
- `sum-overlaps`: Clips each interval but still adds overlap twice.
- `mutate-input`: Correct totals but sorts caller-owned data.

Limitations:
- Public answers are visible; use this for learning and pipeline validation, not model ranking.
- Integer-minute intervals only; this does not evaluate timezone handling or database integration.
