# Task authoring guide

Keep real task directories outside this public repository or in a separate
private repository. Objective tasks contain held-out tests and a known-good
solution; preference tasks contain private prompts, rubrics, and review
material. Publishing them can leak benchmark answers or personal evaluation
criteria.

Each task is a directory under `tasks/`:

```
tasks/fix-date-parse/
├── task.yaml        # metadata (schema below)
├── prompt.md        # what the agent is told - the task specification
├── tests.patch      # held-out tests, applied at grading time only
└── solution.patch   # the known-good fix, used by the smoke gate
```

## task.yaml

```yaml
id: fix-date-parse              # must equal the directory name
category: bugfix                # groups tasks for per-category routing
repo:
  url: /home/me/code/myrepo     # anything `git clone` accepts
  base_commit: <sha>            # the state the agent starts from
prompt_file: prompt.md
tests:
  patch_file: tests.patch
  command: python -m pytest tests/ -x -q
  timeout_seconds: 600
environment:
  runner: docker                # docker (recommended) or local
  image: python:3.11-slim       # must contain the repo's dependencies
solution:
  patch_file: solution.patch
```

## Writing a good prompt

The prompt is the task specification an agent gets with no other context.
Write it the way you'd brief a competent colleague who has the repo checked
out but wasn't in the room:

- **Do** describe the symptom, how to reproduce it, and roughly where to
  look. Include the acceptance criterion in behavioral terms.
- **Don't** paste the solution, name the exact line to change, or mention
  that held-out tests exist and what they check.
- **Don't** leave the scaffolded commit message as the prompt — a commit
  message describes what was done; a prompt describes what is needed.
  Validation rejects prompts containing `TODO` for exactly this reason.

## Grading rules (what agents can and cannot do)

- The agent works in a fresh clone at `base_commit` and may edit anything.
- Before grading, any changes to files touched by `tests.patch` are
  **reverted**, then the held-out tests are applied and run. Rewriting the
  tests therefore never passes.
- Pass = the test command exits 0 within the timeout.

## The smoke gate

`bench smoke` grades two candidates per task and both must behave:

1. `solution.patch` → must **pass** (environment and tests still work)
2. empty diff → must **fail** (the tests actually detect the problem)

Run it after authoring a task and before every snapshot. A task that fails
the gate is broken; fix it or move it out of `tasks/`.

## Preference tasks

Use preference grading when the output is subjective and cannot honestly be
reduced to a held-out test. Replace `tests` and `solution` with:

```yaml
grader:
  type: preference
  artifact: answer.md
  rubric_file: rubric.md
environment:
  runner: local
```

The prompt tells the agent to create `answer.md`; `rubric.md` is not shown to
the contender. `grader.artifact` must be a safe relative path: absolute paths,
parent traversal, direct symlink artifacts, paths that resolve outside the
checkout, directories, missing files, and empty files are rejected. The smoke
gate passes only when the artifact is absent at the base commit; an empty or
unsafe baseline artifact is a task error rather than a successful smoke check.

A successful trial stores the captured output as `artifact.md`, writes the
capture status to `grade.log`, and records `grader_type: preference`,
`passed: null`, and `grade_reason: preference_ready` in `result.json`. Missing,
empty, or unsafe artifacts remain failed captures and are not eligible for a
review pair.

After a run, `bench preference prepare` creates blinded A/B packets for exactly
two configurations. The reviewer records `A`, `B`, `tie`, or `neither` plus a
rationale in `judgment.yaml`; `bench preference report` resolves the hidden
labels and aggregates manual judgments. Reported costs include only trials in
the prepared review pairs.

The hidden `.keys` directory maps A/B labels to configuration IDs and stores
hashes of the prompt, rubric, and candidates. Do not inspect it before judging.
A completed judgment cannot be reused when any hashed material changes. To
review changed material, reset `winner` to `null`, clear the rationale, rerun
`prepare`, and judge the refreshed packet.

Preference results measure taste among produced artifacts. They are reported
separately and never count as correctness passes.

## Choosing tasks

- Prefer commits that fixed something real, with tests written at the time.
- Match the category mix from `bench mine transcripts` — the suite should
  look like the work you actually delegate.
- Keep the repo state self-contained: pin the Docker image, avoid tests that
  need network access (grading runs with `--network=none`).
- 25-30 tasks is enough for coarse routing decisions; below ~6 trials per
  category the report will say `insufficient_data` rather than guess.
