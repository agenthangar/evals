# Security

## Supported versions

Security fixes are released for the latest `1.x` version.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use the repository's
[private vulnerability reporting form](https://github.com/AgentHangar/evals/security/advisories/new)
and include reproduction steps and impact. Reports are visible only to the
repository maintainers until they coordinate a fix and disclosure with you.

## Protecting benchmark data

Task packs contain held-out tests, known-good solutions, prompts, rubrics, and
private repository locations. Preference artifacts and judgments may reveal
personal evaluation criteria. Store real task packs, product configuration,
transcripts, raw outputs, blinded review packets, judgments, and reports in a
separate private workspace. Never commit them to this repository, even briefly.

Preference review directories contain a hidden `.keys` directory that maps
anonymous A/B labels back to product configurations. Treat it as private and do
not inspect or share it before review is complete. The hashes stored there
detect accidental packet changes; they are an integrity check, not encryption
or an access-control boundary.

Agent harnesses execute third-party CLIs against working copies of code. The
Claude Code, Codex, and Cursor harnesses intentionally use unrestricted,
unattended permission modes so trials can finish without human approval. The
agent therefore has the access of the user running `bench`. Use this carefully:
run only task packs, prompts, repositories, test commands, Docker images, and
agent CLI configurations you trust, and be mindful of credentials and sensitive
files available on your computer. Docker grading uses networking disabled, but
it isolates only the grading command—not the agent that produces the candidate
change.

Transcript surveying reads local session files. An `--output` export contains
cleaned prompts and responses plus metadata such as local paths and source file
locations. Inspect the selected directory before running it and do not publish
the resulting material. This repository ignores files named
`*-candidates.jsonl`, but gitignore is only a safeguard: exports with other
names, exports written elsewhere, and copies can still be committed or shared.
